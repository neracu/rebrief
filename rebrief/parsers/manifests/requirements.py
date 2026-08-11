from __future__ import annotations

import re
from pathlib import Path

from rebrief.parsers.manifests.base import ManifestParseResult, empty_result

_REQUIREMENT_NAME_RE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)")


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
        if stripped.startswith(("-r", "--requirement", "-e", "--editable")):
            continue

        match = _REQUIREMENT_NAME_RE.match(stripped)
        if match:
            dependencies.append(match.group(1))

    return {"dependencies": dependencies}
