from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Iterator, TypedDict

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

MAX_DEPTH = 3
SKIP_DIRS: frozenset[str] = frozenset(
    {
        "node_modules",
        "venv",
        ".venv",
        "env",
        "dist",
        "build",
        ".git",
    }
)

_REQUIREMENT_NAME_RE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)")
_PYPROJECT_DEPENDENCY_RE = re.compile(r'"([^"]+)"')


class StackResult(TypedDict):
    languages: list[str]
    manifests: list[str]
    frameworks: list[str]
    dependencies: list[str]
    is_empty: bool


class StackParser:
    def __init__(self, repo_path: str) -> None:
        self._repo_path = Path(repo_path)

    def parse(self) -> StackResult:
        is_empty = not any(True for _ in self._walk_files())
        manifest_paths = self._find_files(MANIFEST_FILES)
        signature_paths = self._find_files(tuple(FRAMEWORK_SIGNATURES.keys()))
        dependencies = self._extract_dependencies(manifest_paths)

        languages = sorted(
            {
                MANIFEST_LANGUAGES[Path(path).name]
                for path in manifest_paths
                if Path(path).name in MANIFEST_LANGUAGES
            }
        )
        frameworks = sorted(
            self._detect_signature_frameworks(signature_paths)
            | self._detect_dependency_frameworks(manifest_paths, signature_paths)
        )

        return {
            "languages": languages,
            "manifests": manifest_paths,
            "frameworks": frameworks,
            "dependencies": dependencies,
            "is_empty": is_empty,
        }

    def _walk_files(self) -> Iterator[Path]:
        if not self._repo_path.is_dir():
            return

        for root, dirs, files in os.walk(self._repo_path):
            root_path = Path(root)
            relative_root = root_path.relative_to(self._repo_path)
            depth = len(relative_root.parts)

            dirs[:] = sorted(
                directory
                for directory in dirs
                if directory not in SKIP_DIRS and depth < MAX_DEPTH
            )

            for filename in sorted(files):
                yield root_path / filename

    def _find_files(self, names: tuple[str, ...]) -> list[str]:
        wanted = set(names)
        found: list[str] = []

        for file_path in self._walk_files():
            if file_path.name not in wanted:
                continue
            found.append(file_path.relative_to(self._repo_path).as_posix())

        return sorted(set(found))

    def _detect_signature_frameworks(self, signature_paths: list[str]) -> set[str]:
        frameworks: set[str] = set()

        for path in signature_paths:
            framework = FRAMEWORK_SIGNATURES.get(Path(path).name)
            if framework is not None:
                frameworks.add(framework)

        return frameworks

    def _detect_dependency_frameworks(
        self,
        manifest_paths: list[str],
        signature_paths: list[str],
    ) -> set[str]:
        frameworks: set[str] = set()

        package_json_paths = [
            path for path in manifest_paths if Path(path).name == "package.json"
        ]
        requirements_paths = [
            path for path in manifest_paths if Path(path).name == "requirements.txt"
        ]

        package_dependencies: set[str] = set()
        for relative_path in package_json_paths:
            package_dependencies.update(
                name.lower()
                for name in self._parse_package_json(self._repo_path / relative_path)
            )

        if "react" in package_dependencies:
            frameworks.add("React")
        if "next" in package_dependencies:
            frameworks.add("Next.js")

        requirement_packages: set[str] = set()
        for relative_path in requirements_paths:
            requirement_packages.update(
                name.lower()
                for name in self._parse_requirements(self._repo_path / relative_path)
            )

        if "django" in requirement_packages:
            frameworks.add("Django")
        if "djangorestframework" in requirement_packages:
            frameworks.add("Django REST Framework")

        if any(Path(path).name == "manage.py" for path in signature_paths):
            frameworks.add("Django")

        return frameworks

    def _extract_dependencies(self, manifest_paths: list[str]) -> list[str]:
        dependencies: list[str] = []

        for relative_path in manifest_paths:
            path = self._repo_path / relative_path
            basename = path.name

            if basename == "package.json":
                dependencies.extend(self._parse_package_json(path))
            elif basename == "requirements.txt":
                dependencies.extend(self._parse_requirements(path))
            elif basename == "pyproject.toml":
                dependencies.extend(self._parse_pyproject(path))

        return sorted(set(dependencies))

    def _parse_package_json(self, path: Path) -> list[str]:
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

    def _parse_requirements(self, path: Path) -> list[str]:
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

    def _parse_pyproject(self, path: Path) -> list[str]:
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
