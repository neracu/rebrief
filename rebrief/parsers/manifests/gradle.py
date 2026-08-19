from __future__ import annotations

import re
from pathlib import Path

from rebrief.parsers.manifests.base import ManifestParseResult, empty_result
from rebrief.parsers.manifests.versions import PackageSpec, parse_gradle_coord


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
    packages: list[PackageSpec] = []
    for match in _GRADLE_DEP_RE.finditer(content):
        coord = match.group(1)
        dependencies.append(coord)
        pkg = parse_gradle_coord(coord)
        if pkg is not None:
            packages.append(pkg)

    result: ManifestParseResult = {"dependencies": dependencies}
    if packages:
        result["packages"] = packages
    return result
