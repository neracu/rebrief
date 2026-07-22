Add visual polish to the utility’s CLI interface using the `rich` library.
Update the `rebrief/cli.py` file.

Requirements:
1. Add `rich` to the list of dependencies in `pyproject.toml` instead of `colorama`.
2. Use `rich.console.Console` to output beautifully formatted text. Replace standard print statements with stylized ones (for example, use emojis and colors: 🔍 [bold cyan]Scanning repository...[/bold cyan]).
3. Implement a live loading indicator (`rich.status.Status` or `Console.status(“...”)`) so that a nice spinner spins while the parsers are running (especially during the resource-intensive `git log` and line-by-line risk search).
4. At the very end of the process, after the file has been created, display a nice summary panel (`rich.panel.Panel`) or table (`rich.table.Table`) in the console with a summary: how many languages were found, how many risks were identified, and the exact path to the generated report file.