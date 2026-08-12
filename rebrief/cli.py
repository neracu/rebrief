import sys
from pathlib import Path

import click
from rich.console import Console

from rebrief import __version__
from rebrief.core.badge import BADGE_LINK, inject_readme_badge
from rebrief.core.confidence import Confidence, parse_min_confidence
from rebrief.core.diff import DiffError, DiffScope, resolve_diff_scope
from rebrief.core.ignore import REBRIEFIGNORE_FILENAME, ensure_rebriefignore
from rebrief.core.remote import (
    RemoteCloneError,
    resolve_remote_target,
    temporary_clone,
)
from rebrief.core.reporter import ReportGenerator
from rebrief.core.scan import run_scan
from rebrief.ui import ScanSettings, ScanUI, make_console


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            pass


_configure_stdio()
console = make_console()


def _default_output(format: str) -> str:
    return "REBRIEF.json" if format == "json" else "REBRIEF.md"


def _join_output(root: Path, resolved_output: str) -> Path:
    output = Path(resolved_output)
    if output.is_absolute():
        return output
    return root / output


def _prepare_repo(repo_path: Path, ui_console: Console | None = None) -> bool:
    """Ensure .rebriefignore exists. Returns True if the file was created."""
    out = ui_console or console
    try:
        return ensure_rebriefignore(repo_path)
    except OSError as exc:
        out.print(f"[yellow]Warning:[/yellow] {exc}")
        return False


def _build_generator(
    repo_path: str | Path,
    min_confidence: Confidence,
    *,
    scan_ui: ScanUI,
    diff_scope: DiffScope | None = None,
) -> ReportGenerator:
    """Run parsers and construct a ReportGenerator for the target repo."""
    with scan_ui.scan_progress() as status:
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
    scan_ui: ScanUI,
    output_root: Path,
    prepare_ignore: bool,
) -> None:
    if prepare_ignore and _prepare_repo(repo, scan_ui.console):
        scan_ui.print_dim(f"  Created {REBRIEFIGNORE_FILENAME} with default exclusions")

    diff_scope: DiffScope | None = None
    if diff_ref is not None:
        try:
            diff_scope = resolve_diff_scope(repo, diff_ref)
        except DiffError as exc:
            scan_ui.print_error(str(exc))
            raise SystemExit(1) from exc

    scan_ui.print_scan_header(
        path=target_label,
        format=format,
        output=resolved_output,
        diff_ref=diff_scope["ref"] if diff_scope is not None else None,
    )

    generator = _build_generator(
        repo,
        parse_min_confidence(min_confidence),
        scan_ui=scan_ui,
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
        scan_ui.print_dim(f"  Badge injected into {readme_path.resolve()}")

    scan_ui.print_results(payload, output_path=output_path)


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
@click.option(
    "--plain",
    "--no-color",
    "plain",
    is_flag=True,
    default=False,
    help="Disable banners, colors, and unicode (script-friendly output).",
)
@click.option(
    "--yes",
    "-y",
    "yes",
    is_flag=True,
    default=False,
    help="Skip the settings panel and start scanning immediately.",
)
def scan(
    target: str,
    format: str,
    output: str | None,
    min_confidence: str,
    inject_badge: bool,
    diff_ref: str | None,
    plain: bool,
    yes: bool,
) -> None:
    settings = ScanSettings(
        target=target,
        format=format.lower(),
        output=output or _default_output(format),
        min_confidence=min_confidence.lower(),
        diff_ref=diff_ref,
        inject_badge=inject_badge,
        output_custom=output is not None,
    )
    write_to_stdout = settings.output == "-"
    ui_file = sys.stderr if write_to_stdout else sys.stdout
    scan_ui = ScanUI.create(plain=plain, file=ui_file)
    scan_ui.print_banner()

    if scan_ui.should_prompt_settings(yes=yes):
        prompted = scan_ui.prompt_settings(settings)
        if prompted is None:
            raise SystemExit(0)
        settings = prompted
        write_to_stdout = settings.output == "-"
        ui_file = sys.stderr if write_to_stdout else sys.stdout
        scan_ui = ScanUI.create(plain=plain, file=ui_file)

    target = settings.target
    format = settings.format
    resolved_output = settings.output
    min_confidence = settings.min_confidence
    inject_badge = settings.inject_badge
    diff_ref = settings.diff_ref

    remote = resolve_remote_target(target)
    if remote is not None:
        if inject_badge:
            scan_ui.print_warning(
                "--inject-badge is ignored for remote repositories."
            )
        scan_ui.console.print(scan_ui.fetch_message(remote.display_name), markup=False)
        try:
            with temporary_clone(
                remote, status=lambda: scan_ui.clone_status(remote.display_name)
            ) as repo:
                _run_scan_command(
                    repo=repo,
                    target_label=target,
                    format=format,
                    resolved_output=resolved_output,
                    write_to_stdout=write_to_stdout,
                    min_confidence=min_confidence,
                    inject_badge=False,
                    diff_ref=diff_ref,
                    scan_ui=scan_ui,
                    output_root=Path.cwd(),
                    prepare_ignore=False,
                )
        except RemoteCloneError as exc:
            scan_ui.print_error(str(exc))
            raise SystemExit(1) from exc
        return

    repo = Path(target).resolve()
    if not repo.is_dir():
        scan_ui.print_error(f"Path does not exist or is not a directory: {target}")
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
        scan_ui=scan_ui,
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
    scan_ui = ScanUI.create(file=sys.stderr)
    repo = Path(repo_path)

    if _prepare_repo(repo, scan_ui.console):
        scan_ui.print_dim(f"  Created {REBRIEFIGNORE_FILENAME} with default exclusions")

    scan_ui.print_dim("Generating badge...")
    generator = _build_generator(
        repo,
        parse_min_confidence(min_confidence),
        scan_ui=scan_ui,
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
