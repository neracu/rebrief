import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from rebrief import __version__
from rebrief.core.badge import BADGE_LINK, inject_readme_badge
from rebrief.core.confidence import Confidence, parse_min_confidence
from rebrief.core.diff import DiffError, DiffScope, resolve_diff_scope
from rebrief.core.ignore import REBRIEFIGNORE_FILENAME, ensure_rebriefignore
from rebrief.core.reporter import ReportGenerator
from rebrief.parsers.git_log import GitLogParser
from rebrief.parsers.risks import RisksParser
from rebrief.parsers.rules import RulesParser
from rebrief.parsers.stack import StackParser


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            pass


def _scan_prefix() -> str:
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    try:
        "🔍".encode(encoding)
    except (UnicodeEncodeError, LookupError):
        return "> "
    return "🔍 "


_configure_stdio()
console = Console()


def _default_output(format: str) -> str:
    return "REBRIEF.json" if format == "json" else "REBRIEF.md"


def _prepare_repo(repo_path: Path) -> bool:
    """Ensure .rebriefignore exists. Returns True if the file was created."""
    try:
        return ensure_rebriefignore(repo_path)
    except OSError as exc:
        console.print(f"[yellow]Warning:[/yellow] {exc}")
        return False


def _build_generator(
    repo_path: str | Path,
    min_confidence: Confidence,
    *,
    ui: Console | None = None,
    diff_scope: DiffScope | None = None,
) -> ReportGenerator:
    """Run parsers and construct a ReportGenerator for the target repo."""
    status_ui = ui or console
    repo = str(repo_path)
    paths = diff_scope["files"] if diff_scope is not None else None
    diff_ref = diff_scope["ref"] if diff_scope is not None else None

    with status_ui.status(
        "[bold cyan]Analyzing technology stack...[/bold cyan]", spinner="dots"
    ):
        stack = StackParser(repo, paths=paths).parse()

    with status_ui.status("[bold cyan]Parsing AI rules...[/bold cyan]", spinner="dots"):
        rules = RulesParser(repo).parse()

    with status_ui.status(
        "[bold cyan]Reading git history...[/bold cyan]", spinner="dots"
    ):
        git_log = GitLogParser(repo, diff_ref=diff_ref).parse()

    with status_ui.status(
        "[bold cyan]Scanning for risks...[/bold cyan]", spinner="dots"
    ):
        risks = RisksParser(
            repo, dependencies=stack["dependencies"], paths=paths
        ).parse()

    return ReportGenerator(
        repo,
        stack,
        rules,
        git_log,
        risks,
        min_confidence=min_confidence,
        diff_scope=diff_scope,
    )


def _badge_html(badge_url: str) -> str:
    return f'<a href="{BADGE_LINK}"><img alt="Rebrief" src="{badge_url}"></a>'


@click.group()
@click.version_option(version=__version__, prog_name="rebrief")
def main() -> None:
    """Audit AI-generated repositories and generate REBRIEF.md handoff reports."""


@main.command()
@click.argument("repo_path", type=click.Path(exists=True, file_okay=False), default=".")
def init(repo_path: str) -> None:
    """Create a default .rebriefignore in the target repository."""
    target = Path(repo_path)
    ignore_path = target / REBRIEFIGNORE_FILENAME

    if ignore_path.is_file():
        console.print(
            f"[dim]{REBRIEFIGNORE_FILENAME} already exists at[/dim] {ignore_path.resolve()}"
        )
        return

    try:
        ensure_rebriefignore(target)
    except OSError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise SystemExit(1) from exc

    console.print(
        f"[bold green]Created[/bold green] {ignore_path.resolve()} "
        f"with default exclusions."
    )


@main.command()
@click.argument("repo_path", type=click.Path(exists=True, file_okay=False), default=".")
@click.option(
    "--format",
    "-f",
    type=click.Choice(["markdown", "json"], case_sensitive=False),
    default="markdown",
    show_default=True,
    help="Output format.",
)
@click.option(
    "--output",
    "-o",
    default=None,
    help="Output path (default: REBRIEF.md or REBRIEF.json). Use '-' for stdout.",
)
@click.option(
    "--min-confidence",
    "-c",
    type=click.Choice(["high", "medium", "low"], case_sensitive=False),
    default="medium",
    show_default=True,
    help="Minimum confidence level for risks included in the report.",
)
@click.option(
    "--inject-badge",
    is_flag=True,
    default=False,
    help="Inject or update a Shields.io badge block in README.md.",
)
@click.option(
    "--diff",
    "diff_ref",
    type=str,
    is_flag=False,
    flag_value="HEAD~1",
    default=None,
    help="Incremental scan against a git ref (default ref: HEAD~1).",
)
def scan(
    repo_path: str,
    format: str,
    output: str | None,
    min_confidence: str,
    inject_badge: bool,
    diff_ref: str | None,
) -> None:
    repo = Path(repo_path)
    resolved_output = output or _default_output(format)
    write_to_stdout = resolved_output == "-"
    ui = Console(file=sys.stderr) if write_to_stdout else console

    if _prepare_repo(repo):
        ui.print(
            f"  [dim]Created {REBRIEFIGNORE_FILENAME} with default exclusions[/dim]"
        )

    diff_scope: DiffScope | None = None
    if diff_ref is not None:
        try:
            diff_scope = resolve_diff_scope(repo, diff_ref)
        except DiffError as exc:
            ui.print(f"[red]Error:[/red] {exc}")
            raise SystemExit(1) from exc

    ui.print(f"{_scan_prefix()}[bold cyan]Scanning repository...[/bold cyan]")
    ui.print(f"  [dim]Path:[/dim]   {repo_path}")
    ui.print(f"  [dim]Format:[/dim] {format}")
    ui.print(f"  [dim]Output:[/dim] {resolved_output}")
    if diff_scope is not None:
        ui.print(f"  [dim]Diff:[/dim]   {diff_scope['ref']}...HEAD")

    generator = _build_generator(
        repo,
        parse_min_confidence(min_confidence),
        ui=ui,
        diff_scope=diff_scope,
    )

    if write_to_stdout:
        content = generator.generate_json() if format == "json" else generator.generate()
        sys.stdout.write(content)
    elif format == "json":
        output_path = repo / resolved_output
        generator.write_json_report(output_path)
    else:
        output_path = repo / resolved_output
        generator.write_report(output_path)

    payload = generator.to_dict()
    if inject_badge:
        readme_path = inject_readme_badge(repo, payload["summary"]["badge_markdown"])
        ui.print(f"  [dim]Badge injected into[/dim] {readme_path.resolve()}")

    table = Table(show_header=False, box=None, padding=(0, 2))
    if diff_scope is not None:
        table.add_row(
            "Mode",
            f"incremental (diff against {diff_scope['ref']})",
        )
        table.add_row(
            "Files scanned",
            f"{diff_scope['files_scanned']} / {diff_scope['files_total']}",
        )
    table.add_row("Languages found", str(payload["summary"]["languages_count"]))
    table.add_row("Risks identified", str(payload["summary"]["risks_count"]))
    report_destination = (
        "(stdout)" if write_to_stdout else str((repo / resolved_output).resolve())
    )
    table.add_row("Report file", report_destination)
    ui.print(Panel(table, title="[bold green]Scan complete[/bold green]", border_style="green"))

@main.command()
@click.argument("repo_path", type=click.Path(exists=True, file_okay=False), default=".")
@click.option(
    "--min-confidence",
    "-c",
    type=click.Choice(["high", "medium", "low"], case_sensitive=False),
    default="medium",
    show_default=True,
    help="Minimum confidence level for risks included in the badge.",
)
def badge(repo_path: str, min_confidence: str) -> None:
    """Print Shields.io Markdown and HTML badge snippets to stdout."""
    ui = Console(file=sys.stderr)
    repo = Path(repo_path)

    if _prepare_repo(repo):
        ui.print(
            f"  [dim]Created {REBRIEFIGNORE_FILENAME} with default exclusions[/dim]"
        )

    ui.print(f"{_scan_prefix()}[bold cyan]Generating badge...[/bold cyan]")
    generator = _build_generator(
        repo,
        parse_min_confidence(min_confidence),
        ui=ui,
    )
    summary = generator.to_dict()["summary"]
    sys.stdout.write(summary["badge_markdown"] + "\n")
    sys.stdout.write(_badge_html(summary["badge_url"]) + "\n")


if __name__ == "__main__":
    main()
