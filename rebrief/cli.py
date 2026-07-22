import click
import colorama

from rebrief import __version__

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


if __name__ == "__main__":
    main()
