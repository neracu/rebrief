Create the basic structure for the open-source CLI tool “rebrief.”

The tool is designed to scan repositories (code) and generate handoff documents for developers.

Follow these steps:

1. Create a LICENSE file containing the text of the standard MIT license (specify the current year, 2026).

2. Create the following directory and file structure:
   ├── rebrief/
   │   ├── __init__.py
   │   └── cli.py
   ├── tests/
   │   ├── __init__.py
   │   └── test_cli.py
   ├── README.md
   └── pyproject.toml

3. Populate `pyproject.toml` with a modern project description. Use a `build-system` based on setuptools or hatch. Specify:
   - Project name: rebrief
   - License: MIT
   - Dependencies: click (or typer), colorama
   - The [project.scripts] section so that the `rebrief` command points to the main function in rebrief.cli:main.

4. Write a concise README.md describing the concept: “rebrief — a CLI utility for locally auditing AI-generated repositories and automatically generating a REBRIEF.md report for active developers.” Add a section with instructions for local installation using `pip install -e .`.

Write only clean files without any extra text, strictly following the structure.