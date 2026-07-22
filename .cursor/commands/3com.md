Prepare the project for publication on PyPI under the name `rebrief`.

Requirements:
1. Check the structure of `pyproject.toml`. Make sure all dependencies (`click`, `rich`) are listed in the `dependencies` section.
2. Verify that an entry point is present so that after installing the package via `pip install rebrief`, the user can immediately run the `rebrief scan` command in the terminal.
3. Create an automated Bash/PowerShell script (or instructions in the `scripts/publish.sh` file) to build and verify the package:
   - Install `build` and `twine`.
   - Run the build command `python -m build`.
   - Verify the validity of the built distributions using `twine check dist/*`.
4. Write an official one-command installation guide in README.md: `pip install rebrief`, along with an example of how to use it.