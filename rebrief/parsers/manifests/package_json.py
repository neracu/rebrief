from __future__ import annotations

import json
from pathlib import Path

from rebrief.parsers.manifests.base import ManifestParseResult, empty_result


def parse(path: Path) -> ManifestParseResult:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        return empty_result(f"Could not read {path.name}: {exc}")
    except json.JSONDecodeError as exc:
        return empty_result(f"Could not parse {path.name}: {exc}")

    dependencies: list[str] = []
    for key in ("dependencies", "devDependencies"):
        section = data.get(key)
        if isinstance(section, dict):
            dependencies.extend(section.keys())

    return {"dependencies": dependencies}
