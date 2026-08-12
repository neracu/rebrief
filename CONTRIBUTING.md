# Contributing to rebrief

Thank you for considering a contribution. **rebrief** is a local CLI that scans any repository and writes a structured `REBRIEF.md` handoff report. The codebase is small and designed to stay approachable.

**Philosophy:** keep it local, lightning-fast, and minimal on dependencies.

- **Local-first** - everything runs on your machine. No cloud uploads, no API keys.
- **Lightning-fast** - static file walks, regex scans, and a single `git` subprocess.
- **Minimal dependencies** - runtime requires only `click` and `rich`. MCP server mode is an optional extra (`pip install "rebrief[mcp]"`).

## How to Help

Areas where community contributions have the most impact:

- **Languages & frameworks** - add parsers for new stacks in `rebrief/parsers/stack.py` (`MANIFEST_FILES`, `FRAMEWORK_SIGNATURES`, dependency heuristics).
- **Secret detection** - improve heuristics in `rebrief/parsers/risks.py` (`KNOWN_SECRET_FORMAT_RE`, `CREDENTIAL_NAME_WORDS`, `_line_has_secret()`, TODO/FIXME markers).
- **Context files** - support new project context filenames in `rebrief/parsers/rules.py` (`RULE_FILES`).

Include matching tests in `tests/` for any parser changes.

`tests/fixtures/secrets/` contains **labeled fake credentials** used only for scanner regression tests (not real secrets).

## Local Development Setup

**Requirements:** Python >= 3.10

```bash
git clone https://github.com/neracu/rebrief
cd rebrief
python -m venv .venv
```

Activate the virtual environment:

- **Windows:** `.venv\Scripts\activate`
- **macOS / Linux:** `source .venv/bin/activate`

Install the package in editable mode with test dependencies:

```bash
pip install -e ".[dev]"
```

## Running Tests

```bash
pytest
```

## Submitting a Pull Request

Before opening a PR:

- `pytest` passes locally
- CLI handles empty folders (`rebrief scan <empty-dir>` exits 0)
- CLI handles folders without Git history (exits 0; report notes point-zero state)

Quick smoke test:

```bash
rebrief scan .
rebrief scan /path/to/empty-folder
```

Questions or early feedback? Open an issue before a large refactor so we can align on approach.