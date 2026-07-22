from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from rebrief import __version__
from rebrief.core.reporter import ReportGenerator
from rebrief.parsers.git_log import GitLogParser
from rebrief.parsers.risks import RiskReport, RisksParser
from rebrief.parsers.rules import RulesParser
from rebrief.parsers.stack import StackParser

console = Console()


def _count_risks(risks: RiskReport) -> int:
    total = len(risks["markers"]) + len(risks["secrets"]) + len(risks["dependency_conflicts"])
    if risks["missing_tests"]:
        total += 1
    return total


@click.group()
@click.version_option(version=__version__, prog_name="rebrief")
def main() -> None:
    """Audit AI-generated repositories and generate REBRIEF.md handoff reports."""


@main.command()
@click.argument("repo_path", type=click.Path(exists=True, file_okay=False), default=".")
@click.option("--output", "-o", default="REBRIEF.md", show_default=True, help="Output report filename.")
def scan(repo_path: str, output: str) -> None:
    console.print("🔍 [bold cyan]Scanning repository...[/bold cyan]")
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

    output_path = Path(repo_path) / output
    ReportGenerator(repo_path, stack, rules, git_log, risks).write_report(output_path)

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_row("Languages found", str(len(stack["languages"])))
    table.add_row("Risks identified", str(_count_risks(risks)))
    table.add_row("Report file", str(output_path.resolve()))
    console.print(Panel(table, title="[bold green]Scan complete[/bold green]", border_style="green"))


if __name__ == "__main__":
    main()
