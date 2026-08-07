# rebrief

[![PyPI version](https://img.shields.io/pypi/v/rebrief.svg)](https://pypi.org/project/rebrief/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

**Instantly turn any unfamiliar repository into a clean developer handoff dossier.**

A local CLI that scans any codebase and produces a structured `REBRIEF.md` report in ~30 seconds - stack, context, history, risks, and a where-to-start checklist.

## Demo

```bash
rebrief scan .
```

![rebrief scan demo](assets/demo.gif)

Point it at any local repo. rebrief walks the stack, rules, git history, and risks, then writes `REBRIEF.md` in the project root.

---

## The Pain

You join a new project - after an outsourcing handoff, a freelancer exit, or years of legacy development. Your first week disappears into onboarding archaeology: manually mapping the tech stack, hunting buried TODOs, sorting through a noisy Git history, and trying to spot security and test gaps before you can ship anything. The knowledge is in the repo; nobody assembled it.

## Before vs. After


| Before                                        | After                                         |
| --------------------------------------------- | --------------------------------------------- |
| A week manually digging through code          | A 30-second local scan                        |
| Guessing project boundaries and setup context | Harvested context from rules files and README |
| Noisy git history hiding real decisions       | Filtered timeline + churn hotspots            |
| Unknown security and test gaps                | Prioritized risk map + developer checklist    |


```bash
rebrief scan .
# → REBRIEF.md
```

---

## Key Features

- **Deep Stack & Manifest Detection** - Recursive scan for `package.json`, `pyproject.toml`, `go.mod`, `Cargo.toml`, and more. Detects languages and frameworks (Django, React, Next.js, Go, and others) across mono-repos and nested layouts.
- **Context & Rules Harvesting** - Extracts local project context from `.cursorrules`, `CLAUDE.md`, `README.md`, and related instruction files so the next developer knows how the project was meant to be built.
- **Noise-Filtered Git Archaeology** - Filters low-value commits (wip, fix typo, minor updates) to surface a cleaner timeline of meaningful changes and 30-day change-density hotspots.
- **Local-First Risk Mapping** - Static analysis for hardcoded secrets, unresolved technical debt (TODO/FIXME), missing test directories, and dependency conflicts. No cloud upload, no API keys.

---

## Installation & Quick Start

```bash
pip install rebrief
```

```bash
rebrief scan .
rebrief scan /path/to/repo -o REBRIEF.md
rebrief init .
```

Scan the current directory (default) or any local path. Output defaults to `REBRIEF.md` in the target repo.

### Excluding paths with `.rebriefignore`

rebrief skips common noise by default (`node_modules`, `.git`, `dist`, `build`, `.next`, `__pycache__`, `.venv`, and similar). To exclude more paths, add a `.rebriefignore` file at the repo root using standard `.gitignore` syntax (globs, `#` comments, one pattern per line).

```bash
rebrief init .   # create a starter .rebriefignore
```

On the first `rebrief scan`, rebrief creates `.rebriefignore` automatically if it is missing. Patterns in that file supplement the built-in defaults — they do not replace them.

---

## Example Output

```markdown
# REBRIEF REPORT: my-app

## 1. Project Overview (Executive Summary)
- This repository uses 1 language(s) and has 4 risk item(s) that need developer attention.
- AI instruction files found: 2 (.cursorrules, CLAUDE.md).
  - `.cursorrules`: 12 lines
  - `CLAUDE.md`: 5 lines

## 2. Technology Stack and Dependencies
- **Languages:** Python
- **Frameworks:** Django
- **Manifests:** pyproject.toml
- **Key dependencies:**
  - `click>=8.1`
  - `django==4.2`

## 3. Solution Timeline (Git History)
- `a1b2c3d` (2026-01-15) Add authentication module — Alice

### Hotspots (Change Density)
- src/app.py: 8 changes

## 4. Risk Map (AI Debt & Security)
### [CRITICAL]
- Hard-coded secret in config.py:3

### [WARNING]
- Missing tests directory (`tests/`, `test/`, or `__tests__/`).
- Duplicate dependency `django` with conflicting versions: ==3.2, ==4.2.

### [INFO]
- TODO in app.py:10

## 5. Developer Checklist ("Where to Start")
1. Review and rotate hard-coded credentials in config.py (line 3).
2. Add a `tests/` directory and cover critical paths.
3. Resolve version conflict for `django`: ==3.2, ==4.2.
4. Set up the development environment for Django.
5. Review frequently changed file: src/app.py (8 edits in 30 days).
```

---

## AI Prompting

After generating `REBRIEF.md`, point your AI assistant at it before diving into the codebase. In Cursor or Claude, use this prompt:

```text
Read REBRIEF.md before starting to understand the project's architecture and hotspots.
```

This gives the model a structured overview of the stack, risks, and where to start - so you spend less time re-explaining the repo on every session.

---

## License

MIT