from __future__ import annotations

import re
import sys
from pathlib import Path

from rebrief.parsers.manifests.base import ManifestParseResult, empty_result
from rebrief.parsers.manifests.versions import PackageSpec, parse_pypi_spec

_PYPROJECT_DEPENDENCY_RE = re.compile(r'"([^"]+)"')


def parse(path: Path) -> ManifestParseResult:
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        return empty_result(f"Could not read {path.name}: {exc}")

    if sys.version_info >= (3, 11):
        return _parse_tomllib(content, path.name)
    return _parse_regex(content)


def _packages_from_specs(specs: list[str]) -> list[PackageSpec]:
    packages: list[PackageSpec] = []
    for spec in specs:
        pkg = parse_pypi_spec(spec)
        if pkg is not None:
            packages.append(pkg)
    return packages


def _parse_tomllib(content: str, filename: str) -> ManifestParseResult:
    import tomllib

    try:
        data = tomllib.loads(content)
    except tomllib.TOMLDecodeError as exc:
        return empty_result(f"Could not parse {filename}: {exc}")

    dependencies: list[str] = []
    package_specs: list[str] = []

    project = data.get("project")
    if isinstance(project, dict):
        project_deps = project.get("dependencies")
        if isinstance(project_deps, list):
            for dep in project_deps:
                dep_str = str(dep)
                dependencies.append(dep_str)
                package_specs.append(dep_str)

        optional_deps = project.get("optional-dependencies")
        if isinstance(optional_deps, dict):
            for group_deps in optional_deps.values():
                if isinstance(group_deps, list):
                    for dep in group_deps:
                        dep_str = str(dep)
                        dependencies.append(dep_str)
                        package_specs.append(dep_str)

    poetry = data.get("tool", {}).get("poetry", {})
    if isinstance(poetry, dict):
        poetry_deps = poetry.get("dependencies")
        if isinstance(poetry_deps, dict):
            for name, version in poetry_deps.items():
                if name.lower() == "python":
                    continue
                dependencies.append(name)
                if isinstance(version, str):
                    spec = version
                    if spec.startswith("^") or spec.startswith("~"):
                        package_specs.append(f"{name}>={spec[1:]}")
                    else:
                        package_specs.append(f"{name}{spec}")
                elif isinstance(version, dict):
                    version_value = version.get("version")
                    if isinstance(version_value, str):
                        if version_value.startswith("^") or version_value.startswith("~"):
                            package_specs.append(f"{name}>={version_value[1:]}")
                        else:
                            package_specs.append(f"{name}{version_value}")

    packages = _packages_from_specs(package_specs)
    result: ManifestParseResult = {"dependencies": dependencies}
    if packages:
        result["packages"] = packages
    return result


def _parse_regex(content: str) -> ManifestParseResult:
    dependencies: list[str] = []
    in_project = False
    in_dependencies = False

    for line in content.splitlines():
        stripped = line.strip()
        if stripped == "[project]":
            in_project = True
            in_dependencies = False
            continue
        if stripped.startswith("[") and stripped != "[project]":
            in_project = False
            in_dependencies = False
            continue
        if in_project and stripped == "dependencies = [":
            in_dependencies = True
            continue
        if in_dependencies:
            if stripped == "]":
                in_dependencies = False
                continue
            dependencies.extend(_PYPROJECT_DEPENDENCY_RE.findall(stripped))

    packages = _packages_from_specs(dependencies)
    result: ManifestParseResult = {"dependencies": dependencies}
    if packages:
        result["packages"] = packages
    return result
