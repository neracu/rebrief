from __future__ import annotations

import re
from pathlib import Path

from rebrief.parsers.manifests.base import ManifestParseResult, empty_result

_GEM_RE = re.compile(r"^\s*gem\s+['\"]([^'\"]+)['\"]")


def parse(path: Path) -> ManifestParseResult:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        return empty_result(f"Could not read {path.name}: {exc}")

    dependencies: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        match = _GEM_RE.match(stripped)
        if match:
            dependencies.append(match.group(1))

    return {"dependencies": dependencies}
