import click
import colorama

from rebrief import __version__

colorama.init()


@click.group()
@click.version_option(version=__version__, prog_name="rebrief")
def main() -> None:
    """Audit AI-generated repositories and generate REBRIEF.md handoff reports."""


if __name__ == "__main__":
    main()
