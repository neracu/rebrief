Write the skeleton for the CLI interface of the `rebrief` utility in the file `rebrief/cli.py`.

Use the `click` library.

Interface requirements:
1. The main entry point is the `main()` function, wrapped in `@click.group()`.
2. There must be a main command, `scan`, which accepts an optional argument specifying the path to the repository (the current directory `.` by default). Example command: `rebrief scan /path/to/repo` or simply `rebrief scan`.
3. Add the `--output` (or `-o`) flag for a custom output file name (default is `REBRIEF.md`).
4. Inside the `scan` command, print some basic output to the console using `click.echo` with color styling (for example, “Scanning repository...”), to verify that it works.
5. Write a simple test in `tests/test_cli.py` using `click.testing.CliRunner` that verifies that the `scan` command runs and returns an exit code of 0.

Submit the completed code for `rebrief/cli.py` and `tests/test_cli.py`.