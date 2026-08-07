import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from rebrief import __version__
from rebrief.core.ignore import REBRIEFIGNORE_FILENAME, ensure_rebriefignore
from rebrief.core.reporter import ReportGenerator
from rebrief.parsers.git_log import GitLogParser
from rebrief.parsers.risks import RiskReport, RisksParser
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


def _count_risks(risks: RiskReport) -> int:
    total = len(risks["markers"]) + len(risks["secrets"]) + len(risks["dependency_conflicts"])
    if risks["missing_tests"]:
        total += 1
    return total


def _prepare_repo(repo_path: Path) -> bool:
    """Ensure .rebriefignore exists. Returns True if the file was created."""
    try:
        return ensure_rebriefignore(repo_path)
    except OSError as exc:
        console.print(f"[yellow]Warning:[/yellow] {exc}")
        return False


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
@click.option("--output", "-o", default="REBRIEF.md", show_default=True, help="Output report filename.")
def scan(repo_path: str, output: str) -> None:
    repo = Path(repo_path)
    if _prepare_repo(repo):
        console.print(
            f"  [dim]Created {REBRIEFIGNORE_FILENAME} with default exclusions[/dim]"
        )

    console.print(f"{_scan_prefix()}[bold cyan]Scanning repository...[/bold cyan]")
    console.print(f"  [dim]Path:[/dim]   {repo_path}")
    console.print(f"  [dim]Output:[/dim] {output}")

    with console.status("[bold cyan]Analyzing technology stack...[/bold cyan]", spinner="dots"):
        stack = StackParser(repo_path).parse()

    with console.status("[bold cyan]Parsing AI rules...[/bold cyan]", spinner="dots"):
        rules = RulesParser(repo_path).parse()

    with console.status("[bold cyan]Reading git history...[/bold cyan]", spinner="dots"):
        git_log = GitLogParser(repo_path).parse()

    with console.status("[bold cyan]Scanning for risks...[/bold cyan]", spinner="dots"):
        risks = RisksParser(repo_path, dependencies=stack["dependencies"]).parse()

    output_path = repo / output
    ReportGenerator(repo_path, stack, rules, git_log, risks).write_report(output_path)

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_row("Languages found", str(len(stack["languages"])))
    table.add_row("Risks identified", str(_count_risks(risks)))
    table.add_row("Report file", str(output_path.resolve()))
    console.print(Panel(table, title="[bold green]Scan complete[/bold green]", border_style="green"))


if __name__ == "__main__":
    main()
