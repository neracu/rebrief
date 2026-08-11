from __future__ import annotations

import re
from pathlib import Path

from rebrief.parsers.manifests.base import ManifestParseResult, empty_result

_GRADLE_DEP_RE = re.compile(
    r"(?:implementation|api|compile|compileOnly|runtimeOnly)\s*"
    r"(?:\(\s*)?['\"]([^'\"]+)['\"]"
)


def parse(path: Path) -> ManifestParseResult:
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        return empty_result(f"Could not read {path.name}: {exc}")

    dependencies: list[str] = []
    for match in _GRADLE_DEP_RE.finditer(content):
        dependencies.append(match.group(1))

    return {"dependencies": dependencies}
