from __future__ import annotations

import json
from pathlib import Path

from rebrief.parsers.manifests.base import ManifestParseResult, empty_result
from rebrief.parsers.manifests.versions import PackageSpec, parse_npm_version


def parse(path: Path) -> ManifestParseResult:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        return empty_result(f"Could not read {path.name}: {exc}")
    except json.JSONDecodeError as exc:
        return empty_result(f"Could not parse {path.name}: {exc}")

    dependencies: list[str] = []
    packages: list[PackageSpec] = []
    for key in ("dependencies", "devDependencies"):
        section = data.get(key)
        if isinstance(section, dict):
            dependencies.extend(section.keys())
            for name, version in section.items():
                if isinstance(version, str):
                    pkg = parse_npm_version(name, version)
                    if pkg is not None:
                        packages.append(pkg)

    result: ManifestParseResult = {"dependencies": dependencies}
    if packages:
        result["packages"] = packages
    return result
