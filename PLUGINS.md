# rebrief Plugin Development Guide

`rebrief` supports custom risk detectors through a small plugin API. Plugins run during the main scan alongside built-in detectors and contribute items to the report `risk_map`.

## Plugin API

Create a class that subclasses `BaseRiskDetector` from `rebrief.plugins.base`:

```python
from rebrief.plugins.base import BaseRiskDetector, RiskItem, ScanContext


class InsecureDebugDetector(BaseRiskDetector):
    name = "insecure-debug"
    description = "Flag DEBUG=True in Django settings modules"

    def scan(self, context: ScanContext) -> list[RiskItem]:
        findings: list[RiskItem] = []
        for path in context.iter_text_files():
            relative = path.relative_to(context.repo_path).as_posix()
            if not relative.endswith("settings.py"):
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            if "DEBUG = True" in text:
                findings.append(
                    {
                        "severity": "warning",
                        "message": f"DEBUG enabled in {relative}",
                        "confidence": "HIGH",
                    }
                )
        return findings
```

### `RiskItem` fields

| Field | Values | Purpose |
|---|---|---|
| `severity` | `critical`, `warning`, `info` | Report section placement |
| `message` | string | Human-readable finding |
| `confidence` | `HIGH`, `MEDIUM`, `LOW` | Filtered by `--min-confidence` / config |

### `ScanContext` (read-only)

| Member | Description |
|---|---|
| `repo_path` | Absolute repository root |
| `stack` | Parsed manifests, dependencies, packages |
| `git_log` | Recent commits and hotspot files |
| `ownership` | Module ownership map |
| `paths` | Diff-scoped file list when incremental |
| `settings` | Entropy cutoff, ignore patterns, secret regexes |
| `iter_text_files()` | Text files respecting ignore rules |
| `repo_root_files()` | Top-level directory entries |

## Local workspace plugins

Place Python modules under `.rebrief/plugins/*.py` in the repository being scanned. Each file may define one or more concrete `BaseRiskDetector` subclasses; `rebrief` instantiates them automatically.

Example layout:

```
my-repo/
  .rebrief/
    plugins/
      insecure_debug.py
  src/
    ...
```

## Publishing pip packages

Register detectors under the `rebrief.plugins` entry point group in `pyproject.toml`:

```toml
[project.entry-points."rebrief.plugins"]
insecure-debug = "my_rebrief_plugins.detectors:InsecureDebugDetector"
```

The entry point may reference a detector class (instantiated with `()`) or a pre-built instance.

Install the package in the environment where `rebrief` runs:

```bash
pip install my-rebrief-plugins
```

## Configuration and CLI

### Disable specific plugins

In `rebrief.toml`:

```toml
[plugins]
disabled = ["markers", "my-custom-plugin"]
```

### Disable all third-party plugins

For strict environments, skip local and pip plugins while keeping built-ins:

```bash
rebrief scan --no-plugins
```

### List active plugins

```bash
rebrief scan --list-plugins
```

Built-in plugins are always listed. External plugins appear when enabled and discoverable.

## Error handling

Plugin load and execution errors are caught automatically. `rebrief` logs a warning to stderr and continues scanning:

```
[WARNING] Plugin 'my-plugin' failed during execution: <error>
```

## Built-in plugins

| Name | Description |
|---|---|
| `secrets` | Hard-coded credentials in source files |
| `markers` | TODO / FIXME / HACK / BUG markers |
| `missing-tests` | Missing `tests/`, `test/`, or `__tests__/` directory |
| `dependency-conflicts` | Conflicting versions in `requirements.txt` / `package.json` |

Built-in names take precedence over external plugins with the same `name`.

## Security note

Plugins execute Python code with the same privileges as the `rebrief` process. Use `--no-plugins` in locked-down CI when you do not trust installed packages or workspace plugin directories.
