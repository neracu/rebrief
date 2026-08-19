from __future__ import annotations

import re
from pathlib import Path

from rebrief.parsers.manifests.base import ManifestParseResult, empty_result
from rebrief.parsers.manifests.versions import PackageSpec, parse_pypi_spec


def parse(path: Path) -> ManifestParseResult:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        return empty_result(f"Could not read {path.name}: {exc}")

    dependencies: list[str] = []
    packages: list[PackageSpec] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith(("-r", "--requirement", "-e", "--editable")):
            continue

        pkg = parse_pypi_spec(stripped)
        if pkg is not None:
            packages.append(pkg)
            dependencies.append(pkg["name"])
            continue

        match = re.match(r"^([A-Za-z0-9][A-Za-z0-9._-]*)", stripped)
        if match:
            dependencies.append(match.group(1))

    result: ManifestParseResult = {"dependencies": dependencies}
    if packages:
        result["packages"] = packages
    return result
