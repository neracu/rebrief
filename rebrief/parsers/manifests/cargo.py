from __future__ import annotations

import re
import sys
from pathlib import Path

from rebrief.parsers.manifests.base import ManifestParseResult, empty_result


def parse(path: Path) -> ManifestParseResult:
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        return empty_result(f"Could not read {path.name}: {exc}")

    if sys.version_info >= (3, 11):
        return _parse_tomllib(content, path.name)
    return _parse_regex(content)


def _parse_tomllib(content: str, filename: str) -> ManifestParseResult:
    import tomllib

    try:
        data = tomllib.loads(content)
    except tomllib.TOMLDecodeError as exc:
        return empty_result(f"Could not parse {filename}: {exc}")

    metadata: dict[str, str] = {}
    dependencies: list[str] = []

    package = data.get("package")
    if isinstance(package, dict):
        name = package.get("name")
        version = package.get("version")
        if isinstance(name, str):
            metadata["name"] = name
        if isinstance(version, str):
            metadata["version"] = version

    for section_name in ("dependencies", "dev-dependencies"):
        section = data.get(section_name)
        if isinstance(section, dict):
            dependencies.extend(section.keys())

    result: ManifestParseResult = {"dependencies": dependencies}
    if metadata:
        result["metadata"] = metadata
    return result


def _parse_regex(content: str) -> ManifestParseResult:
    metadata: dict[str, str] = {}
    dependencies: list[str] = []
    in_package = False
    in_dependencies = False
    in_dev_dependencies = False

    for line in content.splitlines():
        stripped = line.strip()
        if stripped == "[package]":
            in_package = True
            in_dependencies = False
            in_dev_dependencies = False
            continue
        if stripped == "[dependencies]":
            in_package = False
            in_dependencies = True
            in_dev_dependencies = False
            continue
        if stripped == "[dev-dependencies]":
            in_package = False
            in_dependencies = False
            in_dev_dependencies = True
            continue
        if stripped.startswith("[") and stripped not in (
            "[package]",
            "[dependencies]",
            "[dev-dependencies]",
        ):
            in_package = False
            in_dependencies = False
            in_dev_dependencies = False
            continue

        if in_package:
            name_match = re.match(r"name\s*=\s*\"([^\"]+)\"", stripped)
            if name_match:
                metadata["name"] = name_match.group(1)
                continue
            version_match = re.match(r"version\s*=\s*\"([^\"]+)\"", stripped)
            if version_match:
                metadata["version"] = version_match.group(1)
                continue

        if in_dependencies or in_dev_dependencies:
            dep_match = re.match(r"^([A-Za-z0-9_-]+)\s*=", stripped)
            if dep_match:
                dependencies.append(dep_match.group(1))

    result: ManifestParseResult = {"dependencies": dependencies}
    if metadata:
        result["metadata"] = metadata
    return result
