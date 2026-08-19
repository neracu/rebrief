from __future__ import annotations

import os
import sys
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager, nullcontext
from dataclasses import dataclass
from pathlib import Path
from typing import IO, TextIO

from rich import box
from rich.align import Align
from rich.console import Console, Group
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.prompt import Prompt
from rich.table import Table
from rich.text import Text

from rebrief.core.reporter import ReportPayload
from rebrief.core.tokens import (
    TokenStats,
    format_brief_cli,
    format_raw_cli,
    format_savings_cli,
)


def _pad_rows(*rows: str) -> tuple[str, ...]:
    width = max(len(row) for row in rows)
    return tuple(row.ljust(width) for row in rows)


def _flatten_mask(mask: str, front: str, side: str) -> str:
    chars: list[str] = []
    for char in mask:
        if char in " \n":
            chars.append(char)
        elif char == "█":
            chars.append(front)
        else:
            chars.append(side)
    return "".join(chars)


# ANSI Shadow letterforms. █ is the face; box-drawing marks the 3D extrusion.
_BANNER_MASK = "\n".join(
    _pad_rows(
        "██████╗ ███████╗██████╗ ██████╗ ██╗███████╗███████╗",
        "██╔══██╗██╔════╝██╔══██╗██╔══██╗██║██╔════╝██╔════╝",
        "██████╔╝█████╗  ██████╔╝██████╔╝██║█████╗  █████╗",
        "██╔══██╗██╔══╝  ██╔══██╗██╔══██╗██║██╔══╝  ██╔══╝",
        "██║  ██║███████╗██████╔╝██║  ██║██║███████╗██║",
        "╚═╝  ╚═╝╚══════╝╚═════╝ ╚═╝  ╚═╝╚═╝╚══════╝╚═╝",
    )
)
BANNER_ART = _flatten_mask(_BANNER_MASK, "█", "▓")
BANNER_ART_ASCII = _flatten_mask(_BANNER_MASK, "#", "\\")
_BANNER_STOPS = ((0x67, 0xE8, 0xF9), (0x22, 0xD3, 0xEE), (0x0E, 0xA5, 0xE9))

SUBTITLE = "Token-Efficient Codebase Briefings for AI Agents"
CHURN_BAR_WIDTH = 12
NONE_DETECTED = "None detected"

SEVERITY_STYLE = {
    "critical": "bold red",
    "warning": "yellow",
    "info": "cyan",
}

_CURSOR_SAVE = "\0337"
_CURSOR_RESTORE = "\0338"
_ERASE_DOWN = "\033[J"

StatusCallback = Callable[[str], AbstractContextManager[object]]
InputFunc = Callable[[str], str]


def default_output_name(format: str) -> str:
    if format == "json":
        return "REBRIEF.json"
    if format == "xml":
        return "REBRIEF.xml"
    if format == "html":
        return "REBRIEF.html"
    return "REBRIEF.md"


@dataclass
class ScanSettings:
    target: str
    format: str
    output: str
    min_confidence: str
    diff_ref: str | None
    inject_badge: bool
    output_custom: bool = False
    skip_vulnerability_check: bool = False
    no_blame: bool = False

    def apply_format(self, format: str) -> None:
        self.format = format
        if not self.output_custom:
            self.output = default_output_name(format)


def resolve_plain(flag: bool, stream: IO[str] | TextIO | None = None) -> bool:
    """True when banners, color, and unicode should be disabled."""
    if flag:
        return True
    if os.environ.get("NO_COLOR"):
        return True
    target = stream if stream is not None else sys.stdout
    isatty = getattr(target, "isatty", None)
    if callable(isatty):
        try:
            return not bool(isatty())
        except OSError:
            return True
    return True


def confidence_label(value: str) -> str:
    if value == "LOW":
        return "[NEEDS_VERIFICATION]"
    return f"[{value}]"


def churn_bar(count: int, max_count: int, *, plain: bool) -> Text:
    if max_count <= 0 or count <= 0:
        filled = 0
    else:
        filled = min(
            CHURN_BAR_WIDTH,
            max(1, round(CHURN_BAR_WIDTH * count / max_count)),
        )
    empty = CHURN_BAR_WIDTH - filled
    ratio = count / max_count if max_count else 0.0
    if ratio > 2 / 3:
        color = "red"
    elif ratio > 1 / 3:
        color = "yellow"
    else:
        color = "green"
    if plain:
        return Text("#" * filled + "-" * empty)
    return Text("█" * filled + "░" * empty, style=color)


def _supports_glyph(console: Console, glyph: str) -> bool:
    encoding = getattr(console.file, "encoding", None) or "utf-8"
    try:
        glyph.encode(encoding)
    except (UnicodeEncodeError, LookupError):
        return False
    return True


def _banner_color(x: int, width: int) -> str:
    if width <= 1:
        r, g, b = _BANNER_STOPS[0]
        return f"#{r:02x}{g:02x}{b:02x}"
    pos = x / (width - 1) * (len(_BANNER_STOPS) - 1)
    index = min(int(pos), len(_BANNER_STOPS) - 2)
    t = pos - index
    start, end = _BANNER_STOPS[index], _BANNER_STOPS[index + 1]
    red = int(start[0] + (end[0] - start[0]) * t)
    green = int(start[1] + (end[1] - start[1]) * t)
    blue = int(start[2] + (end[2] - start[2]) * t)
    return f"#{red:02x}{green:02x}{blue:02x}"


def _shade(color: str, factor: float) -> str:
    red = max(0, min(255, int(int(color[1:3], 16) * factor)))
    green = max(0, min(255, int(int(color[3:5], 16) * factor)))
    blue = max(0, min(255, int(int(color[5:7], 16) * factor)))
    return f"#{red:02x}{green:02x}{blue:02x}"


def _paint_banner(mask: str, *, front: str, side: str) -> Text:
    lines = mask.split("\n")
    width = max(len(line) for line in lines)
    painted = Text()
    for row, line in enumerate(lines):
        if row:
            painted.append("\n")
        for x, char in enumerate(line.ljust(width)):
            if char == " ":
                painted.append(" ")
            elif char == "█":
                painted.append(front, style=f"bold {_banner_color(x, width)}")
            else:
                painted.append(side, style=_shade(_banner_color(x, width), 0.38))
    return painted


def _join_or_none(values: list[str]) -> str:
    return ", ".join(values) if values else NONE_DETECTED


class _PrintStep:
    def __init__(self, console: Console, message: str) -> None:
        self._console = console
        self._message = message

    def __enter__(self) -> _PrintStep:
        self._console.print(self._message)
        return self

    def __exit__(self, *exc: object) -> bool:
        return False


class _ProgressStep:
    def __init__(self, progress: Progress, task_id: int, message: str) -> None:
        self._progress = progress
        self._task_id = task_id
        self._message = message

    def __enter__(self) -> _ProgressStep:
        self._progress.update(self._task_id, description=self._message)
        return self

    def __exit__(self, *exc: object) -> bool:
        self._progress.advance(self._task_id)
        return False


class _ProgressStatus:
    def __init__(self, progress: Progress, task_id: int) -> None:
        self._progress = progress
        self._task_id = task_id

    def __call__(self, message: str) -> AbstractContextManager[object]:
        return _ProgressStep(self._progress, self._task_id, message)


class ScanUI:
    """Rich terminal presentation for `rebrief scan`."""

    def __init__(self, console: Console, *, plain: bool) -> None:
        self.console = console
        self.plain = plain

    @classmethod
    def create(cls, *, plain: bool = False, file: IO[str] | TextIO | None = None) -> ScanUI:
        resolved = resolve_plain(plain, file)
        console = Console(
            file=file,
            no_color=resolved,
            highlight=False,
            emoji=not resolved,
            legacy_windows=resolved,
        )
        return cls(console, plain=resolved)

    def print_banner(self) -> None:
        if self.plain:
            self.console.print(f"rebrief — {SUBTITLE}")
            return

        if _supports_glyph(self.console, "█▓"):
            painted = _paint_banner(_BANNER_MASK, front="█", side="▓")
        else:
            painted = _paint_banner(_BANNER_MASK, front="#", side="\\")
        title = Align.center(painted)
        rule_char = "─" if _supports_glyph(self.console, "─") else "-"
        rule_width = max(len(line) for line in painted.plain.split("\n"))
        rule = Align.center(Text(rule_char * rule_width, style="dim cyan"))
        subtitle = Text()
        if _supports_glyph(self.console, "⚡"):
            subtitle.append("⚡ ", style="yellow")
        subtitle.append(SUBTITLE, style="dim")
        self.console.print(
            Panel(
                Group(title, Text(""), rule, Align.center(subtitle)),
                box=box.ROUNDED,
                border_style="cyan",
                padding=(1, 3),
            )
        )

    def banner_art(self) -> str:
        sample = "█▓"
        if _supports_glyph(self.console, sample):
            return BANNER_ART
        return BANNER_ART_ASCII

    def should_prompt_settings(
        self,
        *,
        yes: bool = False,
        stdin: IO[str] | TextIO | None = None,
    ) -> bool:
        if yes or self.plain:
            return False
        if os.environ.get("CI"):
            return False
        in_stream = stdin if stdin is not None else sys.stdin
        isatty = getattr(in_stream, "isatty", None)
        if not callable(isatty):
            return False
        try:
            if not isatty():
                return False
        except OSError:
            return False
        return bool(self.console.is_terminal)

    def print_settings_panel(
        self,
        settings: ScanSettings,
        hint: str = "[s] Start scan    [q] Quit",
    ) -> None:
        table = Table(
            box=box.SIMPLE_HEAD,
            show_header=False,
            padding=(0, 1),
        )
        table.add_column("Key", style="bold cyan", no_wrap=True)
        table.add_column("Field", style="dim", no_wrap=True)
        table.add_column("Value", overflow="fold")
        table.add_row("[1]", "Target", settings.target)
        table.add_row("[2]", "Format", settings.format)
        table.add_row("[3]", "Output", settings.output)
        table.add_row("[4]", "Min confidence", settings.min_confidence)
        table.add_row("[5]", "Diff", settings.diff_ref or "off")
        table.add_row("[6]", "Inject badge", "yes" if settings.inject_badge else "no")
        table.add_row(
            "[7]",
            "Vulnerability check",
            "skip" if settings.skip_vulnerability_check else "on",
        )
        table.add_row(
            "[8]",
            "Git blame",
            "skip" if settings.no_blame else "on",
        )
        self.console.print(
            Panel(
                Group(table, Text(""), Text(hint, style="dim")),
                title="[bold]Scan settings[/bold]",
                border_style="cyan",
                box=box.ROUNDED,
            )
        )

    def _settings_stream(self) -> IO[str] | TextIO:
        return self.console.file or sys.stdout

    def _anchor_settings_region(self) -> None:
        stream = self._settings_stream()
        stream.write(_CURSOR_SAVE)
        stream.flush()

    def _replace_settings_region(self) -> None:
        stream = self._settings_stream()
        stream.write(_CURSOR_RESTORE + _ERASE_DOWN)
        stream.flush()

    def prompt_settings(
        self,
        settings: ScanSettings,
        *,
        input_func: InputFunc | None = None,
    ) -> ScanSettings | None:
        """Interactive settings loop. Returns None if the user quits."""
        replace = input_func is None and not self.plain and bool(self.console.is_terminal)

        def ask(
            message: str,
            *,
            default: str | None = None,
            choices: list[str] | None = None,
        ) -> str:
            if input_func is not None:
                value = input_func(message)
                if value == "" and default is not None:
                    return default
                return value
            return Prompt.ask(
                message,
                default=default,
                choices=choices,
                console=self.console,
                show_default=default is not None,
            )

        def show_panel(hint: str = "[s] Start scan    [q] Quit") -> None:
            if replace:
                self._replace_settings_region()
            self.print_settings_panel(settings, hint)

        if replace:
            self._anchor_settings_region()

        hint = "[s] Start scan    [q] Quit"
        while True:
            show_panel(hint)
            hint = "[s] Start scan    [q] Quit"
            choice = ask(
                "Select [1-8], s to start, q to quit",
                default="s",
            ).strip().lower()
            if choice in {"s", "start"}:
                if replace:
                    self._replace_settings_region()
                return settings
            if choice in {"q", "quit"}:
                if replace:
                    self._replace_settings_region()
                return None
            if choice == "1":
                settings.target = ask("Target", default=settings.target).strip() or settings.target
            elif choice == "2":
                selected = ask(
                    "Format",
                    default=settings.format,
                    choices=["markdown", "json", "xml", "html"],
                ).strip().lower()
                if selected in {"markdown", "json", "xml", "html"}:
                    settings.apply_format(selected)
            elif choice == "3":
                selected = ask("Output path", default=settings.output).strip()
                if selected:
                    settings.output = selected
                    settings.output_custom = True
            elif choice == "4":
                selected = ask(
                    "Min confidence",
                    default=settings.min_confidence,
                    choices=["high", "medium", "low"],
                ).strip().lower()
                if selected in {"high", "medium", "low"}:
                    settings.min_confidence = selected
            elif choice == "5":
                selected = ask(
                    "Diff ref (empty to disable)",
                    default=settings.diff_ref or "",
                ).strip()
                settings.diff_ref = selected or None
            elif choice == "6":
                selected = ask(
                    "Inject README badge",
                    default="y" if settings.inject_badge else "n",
                    choices=["y", "n"],
                ).strip().lower()
                settings.inject_badge = selected in {"y", "yes"}
            elif choice == "7":
                selected = ask(
                    "Vulnerability check",
                    default="n" if settings.skip_vulnerability_check else "y",
                    choices=["y", "n"],
                ).strip().lower()
                settings.skip_vulnerability_check = selected in {"n", "no"}
            elif choice == "8":
                selected = ask(
                    "Git blame",
                    default="n" if settings.no_blame else "y",
                    choices=["y", "n"],
                ).strip().lower()
                settings.no_blame = selected in {"n", "no"}
            else:
                hint = "Unknown choice. Use 1-8, s, or q."

    def print_scan_header(
        self,
        *,
        path: str,
        format: str,
        output: str,
        diff_ref: str | None = None,
    ) -> None:
        self.console.print(Text.assemble(("  Path:   ", "dim"), path))
        self.console.print(Text.assemble(("  Format: ", "dim"), format))
        self.console.print(Text.assemble(("  Output: ", "dim"), output))
        if diff_ref is not None:
            self.console.print(Text.assemble(("  Diff:   ", "dim"), f"{diff_ref}...HEAD"))

    def print_dim(self, message: str) -> None:
        self.console.print(Text(message, style="dim"))

    def print_error(self, message: str) -> None:
        self.console.print(Text.assemble(("Error: ", "bold red"), message))

    def print_warning(self, message: str) -> None:
        self.console.print(Text.assemble(("Warning: ", "yellow"), message))

    def fetch_message(self, display_name: str) -> str:
        prefix = ""
        if not self.plain and _supports_glyph(self.console, "⏳"):
            prefix = "⏳ "
        else:
            prefix = "> "
        return f"{prefix}Fetching remote repository [{display_name}]..."

    def clone_status(self, display_name: str) -> AbstractContextManager[object]:
        if self.plain:
            return nullcontext()
        return self.console.status(Text(self.fetch_message(display_name)), spinner="dots")

    @contextmanager
    def scan_progress(self) -> Iterator[StatusCallback]:
        if self.plain:
            yield lambda message: _PrintStep(self.console, message)
            return

        with Progress(
            SpinnerColumn(spinner_name="dots"),
            TextColumn("[bold cyan]{task.description}"),
            TimeElapsedColumn(),
            console=self.console,
            transient=True,
        ) as progress:
            task_id = progress.add_task("Scanning...", total=4)
            yield _ProgressStatus(progress, task_id)

    def print_results(
        self,
        payload: ReportPayload,
        *,
        output_path: Path | None,
    ) -> None:
        self._print_tech_stack(payload)
        self._print_hotspots(payload)
        self._print_ownership_map(payload)
        self._print_risk_map(payload)
        self._print_token_savings(payload["summary"]["token_stats"])
        self.print_completion(
            output_path=output_path,
            brief_tokens=payload["summary"]["token_stats"]["brief_tokens"],
        )

    def print_completion(self, *, output_path: Path | None, brief_tokens: int) -> None:
        destination = "stdout" if output_path is None else output_path.name
        line = f"saved to {destination} ({format_brief_cli(brief_tokens)})"
        if self.plain:
            self.console.print(line)
            return
        self.console.print(
            Panel(
                Text(line, justify="center"),
                title="[bold green]Done[/bold green]",
                border_style="green",
                box=box.ROUNDED,
            )
        )

    def _print_tech_stack(self, payload: ReportPayload) -> None:
        stack = payload["tech_stack"]
        summary = payload["summary"]
        table = Table(
            title="Tech Stack & Overview",
            box=box.SIMPLE_HEAD,
            show_header=True,
            header_style="bold",
            padding=(0, 1),
        )
        table.add_column("Field", style="dim", no_wrap=True)
        table.add_column("Value", overflow="fold")

        if payload["mode"] == "incremental":
            ref = payload["diff_ref"] or "HEAD~1"
            table.add_row("Mode", f"incremental (diff against {ref})")
            table.add_row(
                "Files scanned",
                f"{summary['files_scanned']} / {summary['files_total']}",
            )

        table.add_row("Languages", _join_or_none(list(stack["languages"])))
        table.add_row("Frameworks", _join_or_none(list(stack["frameworks"])))
        table.add_row("Manifests", _join_or_none(list(stack["manifests"])))

        context_files = list(summary["ai_instruction_files"])
        if context_files:
            table.add_row(
                "Context files",
                f"{len(context_files)} ({', '.join(context_files)})",
            )
        else:
            table.add_row("Context files", "none")

        self.console.print(table)

    def _print_hotspots(self, payload: ReportPayload) -> None:
        hotspots = payload["timeline"]["hotspots"]
        table = Table(
            title="Hotspots",
            box=box.SIMPLE_HEAD,
            show_header=True,
            header_style="bold",
            padding=(0, 1),
        )
        table.add_column("File", overflow="fold")
        table.add_column("Changes", justify="right", no_wrap=True)
        table.add_column("Churn", no_wrap=True)

        if not hotspots:
            table.add_row(Text(NONE_DETECTED, style="dim"), "", "")
        else:
            max_count = max(item["changes"] for item in hotspots)
            for item in hotspots:
                table.add_row(
                    item["file"],
                    str(item["changes"]),
                    churn_bar(item["changes"], max_count, plain=self.plain),
                )

        self.console.print(table)

    def _print_ownership_map(self, payload: ReportPayload) -> None:
        ownership_map = payload.get("ownership_map", {})
        if not ownership_map:
            return

        table = Table(
            title="Code Ownership",
            box=box.SIMPLE_HEAD,
            show_header=True,
            header_style="bold",
            padding=(0, 1),
        )
        table.add_column("Module", overflow="fold")
        table.add_column("Primary", no_wrap=True)
        table.add_column("Secondary / AI", overflow="fold")
        table.add_column("Expertise", no_wrap=True)

        from rebrief.parsers.ownership import format_secondary_display

        for module_path in sorted(ownership_map):
            entry = ownership_map[module_path]
            secondary = format_secondary_display(
                secondary=entry["secondary"],
                secondary_percent=entry["secondary_percent"],
                ai_assisted=entry["ai_assisted"],
                ai_percent=entry["ai_percent"],
                ai_tools=entry["ai_tools"],
            )
            table.add_row(
                module_path,
                f"{entry['primary_owner']} ({entry['primary_percent']:.0f}%)",
                secondary,
                entry["expertise_level"],
            )

        self.console.print(table)

    def _print_risk_map(self, payload: ReportPayload) -> None:
        table = Table(
            title="Risk Map",
            box=box.SIMPLE_HEAD,
            show_header=True,
            header_style="bold",
            padding=(0, 1),
        )
        table.add_column("Severity", no_wrap=True)
        table.add_column("Confidence", no_wrap=True)
        table.add_column("Message", overflow="fold")

        rows = 0
        for key in ("critical", "warning", "info"):
            style = SEVERITY_STYLE[key]
            label = key.upper()
            for item in payload["risk_map"][key]:
                table.add_row(
                    Text(label, style=style),
                    Text(confidence_label(item["confidence"])),
                    Text(item["message"]),
                )
                rows += 1

        if rows == 0:
            table.add_row(Text(NONE_DETECTED, style="dim"), "", "")

        self.console.print(table)

    def _print_token_savings(self, stats: TokenStats) -> None:
        body = Table(show_header=False, box=None, padding=(0, 1))
        body.add_column(style="dim", no_wrap=True)
        body.add_column()
        body.add_row("Raw", format_raw_cli(stats["raw_codebase_tokens"]))
        body.add_row("Brief", format_brief_cli(stats["brief_tokens"]))
        body.add_row("Saved", format_savings_cli(stats["savings_percentage"]))

        title = "Token Savings"
        if self.plain:
            self.console.print(title)
            self.console.print(body)
            return

        self.console.print(
            Panel(
                body,
                title=title,
                border_style="magenta",
                box=box.ROUNDED,
            )
        )


def make_console(*, plain: bool = False, file: IO[str] | TextIO | None = None) -> Console:
    """Shared Console for non-scan commands (init)."""
    resolved = resolve_plain(plain, file)
    return Console(
        file=file,
        no_color=resolved,
        highlight=False,
        emoji=not resolved,
        legacy_windows=True,
    )
