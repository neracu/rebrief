import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from rebrief import __version__
from rebrief.core.badge import BADGE_LINK, inject_readme_badge
from rebrief.core.confidence import Confidence, parse_min_confidence
from rebrief.core.diff import DiffError, DiffScope, resolve_diff_scope
from rebrief.core.ignore import REBRIEFIGNORE_FILENAME, ensure_rebriefignore
from rebrief.core.remote import (
    RemoteCloneError,
    RemoteTarget,
    resolve_remote_target,
    temporary_clone,
)
from rebrief.core.reporter import ReportGenerator
from rebrief.core.scan import run_scan
from rebrief.core.tokens import (
    TokenStats,
    format_brief_cli,
    format_raw_cli,
    format_savings_cli,
)


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            pass


def _emoji_prefix(emoji: str, fallback: str = "> ") -> str:
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    try:
        emoji.encode(encoding)
    except (UnicodeEncodeError, LookupError):
        return fallback
    return f"{emoji} "


def _scan_prefix() -> str:
    return _emoji_prefix("🔍")


def _fetch_prefix() -> str:
    return _emoji_prefix("⏳")


def _token_prefix() -> str:
    return _emoji_prefix("⚡")


def _fetch_message(display_name: str) -> str:
    return f"{_fetch_prefix()}Fetching remote repository [{display_name}]..."


_configure_stdio()
console = Console()


def _default_output(format: str) -> str:
    return "REBRIEF.json" if format == "json" else "REBRIEF.md"


def _join_output(root: Path, resolved_output: str) -> Path:
    output = Path(resolved_output)
    if output.is_absolute():
        return output
    return root / output


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

    def status(message: str) -> object:
        return status_ui.status(f"[bold cyan]{message}[/bold cyan]", spinner="dots")

    return run_scan(
        repo_path,
        min_confidence,
        diff_scope=diff_scope,
        status=status,
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


def _run_scan_command(
    *,
    repo: Path,
    target_label: str,
    format: str,
    resolved_output: str,
    write_to_stdout: bool,
    min_confidence: str,
    inject_badge: bool,
    diff_ref: str | None,
    ui: Console,
    output_root: Path,
    prepare_ignore: bool,
) -> None:
    if prepare_ignore and _prepare_repo(repo):
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
    ui.print(f"  [dim]Path:[/dim]   {target_label}")
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

    output_path: Path | None = None
    if write_to_stdout:
        content = generator.generate_json() if format == "json" else generator.generate()
        sys.stdout.write(content)
    else:
        output_path = _join_output(output_root, resolved_output)
        if format == "json":
            generator.write_json_report(output_path)
        else:
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
        "(stdout)" if output_path is None else str(output_path.resolve())
    )
    table.add_row("Report file", report_destination)
    ui.print(Panel(table, title="[bold green]Scan complete[/bold green]", border_style="green"))
    _print_token_efficiency(ui, payload["summary"]["token_stats"])


def _print_token_efficiency(ui: Console, stats: TokenStats) -> None:
    raw = format_raw_cli(stats["raw_codebase_tokens"])
    brief = format_brief_cli(stats["brief_tokens"])
    reduction = format_savings_cli(stats["savings_percentage"])
    ui.print(f"{_token_prefix()}[bold]Token Efficiency:[/bold]")
    ui.print(f"   └─ Raw Codebase: {raw}")
    ui.print(f"   └─ REBRIEF.md:    {brief}")
    ui.print(f"   └─ Reduction:    {reduction}")


def _clone_status(ui: Console, remote: RemoteTarget) -> object:
    return ui.status(Text(_fetch_message(remote.display_name)), spinner="dots")


@main.command()
@click.argument("target", default=".")
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
    target: str,
    format: str,
    output: str | None,
    min_confidence: str,
    inject_badge: bool,
    diff_ref: str | None,
) -> None:
    resolved_output = output or _default_output(format)
    write_to_stdout = resolved_output == "-"
    ui = Console(file=sys.stderr) if write_to_stdout else console

    remote = resolve_remote_target(target)
    if remote is not None:
        if inject_badge:
            ui.print(
                "[yellow]Warning:[/yellow] --inject-badge is ignored for remote "
                "repositories."
            )
        ui.print(_fetch_message(remote.display_name), markup=False)
        try:
            with temporary_clone(remote, status=lambda: _clone_status(ui, remote)) as repo:
                _run_scan_command(
                    repo=repo,
                    target_label=target,
                    format=format,
                    resolved_output=resolved_output,
                    write_to_stdout=write_to_stdout,
                    min_confidence=min_confidence,
                    inject_badge=False,
                    diff_ref=diff_ref,
                    ui=ui,
                    output_root=Path.cwd(),
                    prepare_ignore=False,
                )
        except RemoteCloneError as exc:
            ui.print(f"[red]Error:[/red] {exc}")
            raise SystemExit(1) from exc
        return

    repo = Path(target).resolve()
    if not repo.is_dir():
        ui.print(
            f"[red]Error:[/red] Path does not exist or is not a directory: {target}"
        )
        raise SystemExit(1)

    _run_scan_command(
        repo=repo,
        target_label=target,
        format=format,
        resolved_output=resolved_output,
        write_to_stdout=write_to_stdout,
        min_confidence=min_confidence,
        inject_badge=inject_badge,
        diff_ref=diff_ref,
        ui=ui,
        output_root=repo,
        prepare_ignore=True,
    )


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


def _import_mcp_run_stdio() -> object:
    from rebrief.mcp.server import run_stdio

    return run_stdio


def _run_mcp_server() -> None:
    try:
        run_stdio = _import_mcp_run_stdio()
    except ImportError:
        from rebrief.mcp import MCP_EXTRA_HINT

        click.echo(MCP_EXTRA_HINT, err=True)
        raise SystemExit(1)
    run_stdio()


@main.group(invoke_without_command=True)
@click.pass_context
def mcp(ctx: click.Context) -> None:
    """Start an MCP server over stdio, or manage client configuration."""
    if ctx.invoked_subcommand is None:
        _run_mcp_server()


@mcp.command("install")
@click.option(
    "--client",
    type=click.Choice(["cursor", "claude", "windsurf", "roo", "all"], case_sensitive=False),
    default="all",
    show_default=True,
    help="Which client config to print or write.",
)
@click.option(
    "--write",
    is_flag=True,
    default=False,
    help="Merge the rebrief MCP entry into the selected client config file(s).",
)
def mcp_install(client: str, write: bool) -> None:
    """Print or inject MCP client configuration for popular IDEs."""
    from rebrief.mcp.install import install_mcp_config

    install_mcp_config(client=client.lower(), write=write)


@main.command("server")
def server() -> None:
    """Alias for `rebrief mcp` — start an MCP server over stdio."""
    _run_mcp_server()


if __name__ == "__main__":
    main()
