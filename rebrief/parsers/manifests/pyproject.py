from __future__ import annotations

import re
import sys
from pathlib import Path

from rebrief.parsers.manifests.base import ManifestParseResult, empty_result

_PYPROJECT_DEPENDENCY_RE = re.compile(r'"([^"]+)"')


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

    dependencies: list[str] = []

    project = data.get("project")
    if isinstance(project, dict):
        project_deps = project.get("dependencies")
        if isinstance(project_deps, list):
            dependencies.extend(str(dep) for dep in project_deps)

        optional_deps = project.get("optional-dependencies")
        if isinstance(optional_deps, dict):
            for group_deps in optional_deps.values():
                if isinstance(group_deps, list):
                    dependencies.extend(str(dep) for dep in group_deps)

    poetry = data.get("tool", {}).get("poetry", {})
    if isinstance(poetry, dict):
        poetry_deps = poetry.get("dependencies")
        if isinstance(poetry_deps, dict):
            dependencies.extend(
                name for name in poetry_deps if name.lower() != "python"
            )

    return {"dependencies": dependencies}


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

    return {"dependencies": dependencies}
