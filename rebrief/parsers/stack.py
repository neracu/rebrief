from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import TypedDict

MANIFEST_FILES: tuple[str, ...] = (
    "package.json",
    "requirements.txt",
    "poetry.lock",
    "pyproject.toml",
    "go.mod",
    "Cargo.toml",
)

MANIFEST_LANGUAGES: dict[str, str] = {
    "package.json": "JavaScript/TypeScript",
    "requirements.txt": "Python",
    "poetry.lock": "Python",
    "pyproject.toml": "Python",
    "go.mod": "Go",
    "Cargo.toml": "Rust",
}

FRAMEWORK_SIGNATURES: dict[str, str] = {
    "next.config.js": "Next.js",
    "next.config.mjs": "Next.js",
    "manage.py": "Django",
    "nuxt.config.js": "Nuxt.js",
    "vite.config.js": "Vite",
}

_REQUIREMENT_NAME_RE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)")
_PYPROJECT_DEPENDENCY_RE = re.compile(r'"([^"]+)"')


class StackResult(TypedDict):
    languages: list[str]
    manifests: list[str]
    frameworks: list[str]
    dependencies: list[str]


class StackParser:
    def __init__(self, repo_path: str) -> None:
        self._repo_path = Path(repo_path)

    def parse(self) -> StackResult:
        manifests = [name for name in MANIFEST_FILES if self._file_exists(name)]
        frameworks = sorted(
            {
                framework
                for signature, framework in FRAMEWORK_SIGNATURES.items()
                if self._file_exists(signature)
            }
        )
        languages = sorted({MANIFEST_LANGUAGES[name] for name in manifests})
        dependencies = self._extract_dependencies(manifests)

        return {
            "languages": languages,
            "manifests": manifests,
            "frameworks": frameworks,
            "dependencies": dependencies,
        }

    def _file_exists(self, name: str) -> bool:
        return (self._repo_path / name).is_file()

    def _extract_dependencies(self, manifests: list[str]) -> list[str]:
        dependencies: list[str] = []

        if "package.json" in manifests:
            dependencies.extend(self._parse_package_json())
        if "requirements.txt" in manifests:
            dependencies.extend(self._parse_requirements())
        if "pyproject.toml" in manifests:
            dependencies.extend(self._parse_pyproject())

        return sorted(set(dependencies))

    def _parse_package_json(self) -> list[str]:
        path = self._repo_path / "package.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []

        dependencies: list[str] = []
        for key in ("dependencies", "devDependencies"):
            section = data.get(key)
            if isinstance(section, dict):
                dependencies.extend(section.keys())
        return dependencies

    def _parse_requirements(self) -> list[str]:
        path = self._repo_path / "requirements.txt"
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []

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
        return dependencies

    def _parse_pyproject(self) -> list[str]:
        path = self._repo_path / "pyproject.toml"
        try:
            content = path.read_text(encoding="utf-8")
        except OSError:
            return []

        if sys.version_info >= (3, 11):
            return self._parse_pyproject_tomllib(content)
        return self._parse_pyproject_regex(content)

    def _parse_pyproject_tomllib(self, content: str) -> list[str]:
        import tomllib

        try:
            data = tomllib.loads(content)
        except tomllib.TOMLDecodeError:
            return []

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

        return dependencies

    def _parse_pyproject_regex(self, content: str) -> list[str]:
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

        return dependencies
