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
    if format == "json":
        return "REBRIEF.json"
    if format == "xml":
        return "REBRIEF.xml"
    if format == "html":
        return "REBRIEF.html"
    return "REBRIEF.md"


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
    skip_vulnerability_check: bool = False,
    no_blame: bool = False,
) -> ReportGenerator:
    """Run parsers and construct a ReportGenerator for the target repo."""
    with scan_ui.scan_progress() as status:
        return run_scan(
            repo_path,
            min_confidence,
            diff_scope=diff_scope,
            status=status,
            skip_vulnerability_check=skip_vulnerability_check,
            no_blame=no_blame,
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
    skip_vulnerability_check: bool = False,
    no_blame: bool = False,
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
        skip_vulnerability_check=skip_vulnerability_check,
        no_blame=no_blame,
    )

    output_path: Path | None = None
    if write_to_stdout:
        if format == "json":
            content = generator.generate_json()
        elif format == "xml":
            content = generator.generate_xml()
        elif format == "html":
            content = generator.generate_html()
        else:
            content = generator.generate()
        sys.stdout.write(content)
    else:
        output_path = _join_output(output_root, resolved_output)
        if format == "json":
            generator.write_json_report(output_path)
        elif format == "xml":
            generator.write_xml_report(output_path)
        elif format == "html":
            generator.write_html_report(output_path)
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
    type=click.Choice(["markdown", "json", "xml", "html"], case_sensitive=False),
    default="markdown",
    show_default=True,
    help="Output format.",
)
@click.option(
    "--output",
    "-o",
    default=None,
    help="Output path (default: REBRIEF.md, REBRIEF.json, REBRIEF.xml, or REBRIEF.html). Use '-' for stdout.",
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
@click.option(
    "--skip-vulnerability-check",
    is_flag=True,
    default=False,
    help="Skip remote OSV API calls (air-gapped / faster local scans).",
)
@click.option(
    "--no-blame",
    is_flag=True,
    default=False,
    help="Skip git blame ownership analysis on large repositories.",
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
    skip_vulnerability_check: bool,
    no_blame: bool,
) -> None:
    settings = ScanSettings(
        target=target,
        format=format.lower(),
        output=output or _default_output(format),
        min_confidence=min_confidence.lower(),
        diff_ref=diff_ref,
        inject_badge=inject_badge,
        output_custom=output is not None,
        skip_vulnerability_check=skip_vulnerability_check,
        no_blame=no_blame,
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
    skip_vulnerability_check = settings.skip_vulnerability_check
    no_blame = settings.no_blame

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
                    skip_vulnerability_check=skip_vulnerability_check,
                    no_blame=no_blame,
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
        skip_vulnerability_check=skip_vulnerability_check,
        no_blame=no_blame,
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


def _import_httpx() -> object:
    import httpx

    return httpx


@main.command("chat")
@click.argument("target", default=".")
@click.option(
    "--model",
    "-m",
    default=None,
    help=(
        "Model id (anthropic/claude-3-5-sonnet, openai/gpt-4o-mini, "
        "gemini/gemini-2.0-flash, openrouter/openai/gpt-4o-mini, ollama/llama3). "
        "Default: first available provider."
    ),
)
@click.option(
    "--key",
    "-k",
    "api_key",
    default=None,
    help="API key override (otherwise ANTHROPIC_API_KEY, OPENAI_API_KEY, GEMINI_API_KEY, OPENROUTER_API_KEY).",
)
@click.option(
    "--file",
    "report_file",
    default=None,
    type=click.Path(dir_okay=False),
    help="Existing REBRIEF.md or REBRIEF.json. If omitted, load cwd/target report or scan.",
)
def chat(target: str, model: str | None, api_key: str | None, report_file: str | None) -> None:
    """Ask questions about a scanned repository using your own LLM API key."""
    try:
        _import_httpx()
    except ImportError:
        from rebrief.chat import CHAT_EXTRA_HINT

        click.echo(CHAT_EXTRA_HINT, err=True)
        raise SystemExit(1)

    from rebrief.chat.context import find_existing_report, load_chat_context
    from rebrief.chat.credentials import ChatError, resolve_auth
    from rebrief.chat.repl import run_repl
    from rebrief.chat.session import ChatSession
    from rebrief.core.envfile import load_env_files

    load_env_files()
    scan_ui = ScanUI.create()
    try:
        auth = resolve_auth(model=model, api_key=api_key)
        needs_scan = report_file is None and find_existing_report(target) is None
        if needs_scan:
            scan_ui.print_banner()
            with scan_ui.scan_progress() as status:
                context = load_chat_context(target, status=status)
        else:
            context = load_chat_context(target, report_file)
    except ChatError as exc:
        scan_ui.print_error(str(exc))
        raise SystemExit(1) from exc
    except RemoteCloneError as exc:
        scan_ui.print_error(str(exc))
        raise SystemExit(1) from exc

    session = ChatSession(context=context, model=auth.model)
    run_repl(session, auth, scan_ui.console)


@main.command("server")
def server() -> None:
    """Alias for `rebrief mcp` — start an MCP server over stdio."""
    _run_mcp_server()


@main.command("serve")
@click.option("--host", default="127.0.0.1", show_default=True, help="Bind address.")
@click.option("--port", default=8000, type=int, show_default=True, help="Bind port.")
@click.option(
    "--open/--no-open",
    "open_browser",
    default=True,
    help="Open the UI in a browser (default: open).",
)
def serve(host: str, port: int, open_browser: bool) -> None:
    """Start the web UI in a browser (requires rebrief[web])."""
    try:
        import uvicorn

        from rebrief.webapp.app import app, browser_url
    except ImportError:
        from rebrief.webapp import WEB_EXTRA_HINT

        click.echo(WEB_EXTRA_HINT, err=True)
        raise SystemExit(1)

    url = browser_url(host, port)
    click.echo(f"rebrief UI: {url}")
    if open_browser:
        import threading
        import webbrowser

        def _open() -> None:
            webbrowser.open(url)

        threading.Timer(0.8, _open).start()
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
