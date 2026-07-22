from pathlib import Path

import click
import colorama

from rebrief import __version__
from rebrief.core.reporter import ReportGenerator
from rebrief.parsers.git_log import GitLogParser
from rebrief.parsers.risks import RisksParser
from rebrief.parsers.rules import RulesParser
from rebrief.parsers.stack import StackParser

colorama.init()


@click.group()
@click.version_option(version=__version__, prog_name="rebrief")
def main() -> None:
    """Audit AI-generated repositories and generate REBRIEF.md handoff reports."""


@main.command()
@click.argument("repo_path", type=click.Path(exists=True, file_okay=False), default=".")
@click.option("--output", "-o", default="REBRIEF.md", show_default=True, help="Output report filename.")
def scan(repo_path: str, output: str) -> None:
    click.echo(click.style("Scanning repository...", fg="cyan"))
    click.echo(f"  Path:   {repo_path}")
    click.echo(f"  Output: {output}")

    stack = StackParser(repo_path).parse()
    rules = RulesParser(repo_path).parse()
    git_log = GitLogParser(repo_path).parse()
    risks = RisksParser(repo_path, dependencies=stack["dependencies"]).parse()

    output_path = Path(repo_path) / output
    ReportGenerator(repo_path, stack, rules, git_log, risks).write_report(output_path)

    click.echo(click.style(f"Report written to {output_path}", fg="green"))


if __name__ == "__main__":
    main()
