from __future__ import annotations

import re
import sys
from pathlib import Path

from rebrief.parsers.manifests.base import ManifestParseResult, empty_result
from rebrief.parsers.manifests.versions import PackageSpec, parse_cargo_version


def parse(path: Path) -> ManifestParseResult:
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        return empty_result(f"Could not read {path.name}: {exc}")

    if sys.version_info >= (3, 11):
        return _parse_tomllib(content, path.name)
    return _parse_regex(content)


def _extract_cargo_packages(section: dict[str, object]) -> list[PackageSpec]:
    packages: list[PackageSpec] = []
    for name, value in section.items():
        if isinstance(value, str):
            spec = value
        elif isinstance(value, dict):
            version = value.get("version")
            spec = str(version) if version is not None else ""
        else:
            continue
        pkg = parse_cargo_version(name, spec)
        if pkg is not None:
            packages.append(pkg)
    return packages


def _parse_tomllib(content: str, filename: str) -> ManifestParseResult:
    import tomllib

    try:
        data = tomllib.loads(content)
    except tomllib.TOMLDecodeError as exc:
        return empty_result(f"Could not parse {filename}: {exc}")

    metadata: dict[str, str] = {}
    dependencies: list[str] = []
    packages: list[PackageSpec] = []

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
            packages.extend(_extract_cargo_packages(section))

    result: ManifestParseResult = {"dependencies": dependencies}
    if metadata:
        result["metadata"] = metadata
    if packages:
        result["packages"] = packages
    return result


def _parse_regex(content: str) -> ManifestParseResult:
    metadata: dict[str, str] = {}
    dependencies: list[str] = []
    packages: list[PackageSpec] = []
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
            name_match = re.match(r'name\s*=\s*"([^"]+)"', stripped)
            if name_match:
                metadata["name"] = name_match.group(1)
                continue
            version_match = re.match(r'version\s*=\s*"([^"]+)"', stripped)
            if version_match:
                metadata["version"] = version_match.group(1)
                continue

        if in_dependencies or in_dev_dependencies:
            dep_match = re.match(r'^([A-Za-z0-9_-]+)\s*=\s*(.+)$', stripped)
            if dep_match:
                name = dep_match.group(1)
                dependencies.append(name)
                pkg = parse_cargo_version(name, dep_match.group(2).strip())
                if pkg is not None:
                    packages.append(pkg)

    result: ManifestParseResult = {"dependencies": dependencies}
    if metadata:
        result["metadata"] = metadata
    if packages:
        result["packages"] = packages
    return result
