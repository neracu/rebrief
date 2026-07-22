# rebrief

rebrief — a CLI utility for locally auditing AI-generated repositories and automatically generating a REBRIEF.md report for active developers.

Scan a repository to surface structural gaps, risky patterns, and missing context, then produce a handoff document that helps the next developer take over with confidence.

## Installation

```bash
pip install rebrief
```

## Usage

```bash
rebrief scan /path/to/repo
rebrief scan . -o REBRIEF.md
rebrief --help
```

## Development

Install in editable mode with test dependencies:

```bash
pip install -e ".[dev]"
pytest
```

Build and validate distributions before publishing:

```bash
bash scripts/publish.sh
```

On Windows PowerShell:

```powershell
.\scripts\publish.ps1
```

Or install publish tooling explicitly:

```bash
pip install -e ".[publish]"
python -m build
python -m twine check dist/*
```
