from __future__ import annotations

import re
from pathlib import Path

from rebrief.parsers.manifests.base import ManifestParseResult, empty_result
from rebrief.parsers.manifests.versions import PackageSpec, parse_gem_version

_GEM_RE = re.compile(r"^\s*gem\s+['\"]([^'\"]+)['\"](?:\s*,\s*['\"]([^'\"]+)['\"])?")


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

        match = _GEM_RE.match(stripped)
        if match:
            name = match.group(1)
            dependencies.append(name)
            version = match.group(2)
            if version:
                pkg = parse_gem_version(name, version)
                if pkg is not None:
                    packages.append(pkg)

    result: ManifestParseResult = {"dependencies": dependencies}
    if packages:
        result["packages"] = packages
    return result
