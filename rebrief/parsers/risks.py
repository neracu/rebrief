from __future__ import annotations

import fnmatch
import json
import os
import re
from collections import defaultdict
from pathlib import Path
from typing import Iterator, TypedDict

TEST_DIRS: tuple[str, ...] = ("tests", "test", "__tests__")
MARKER_RE = re.compile(r"\b(TODO|FIXME|HACK|BUG)\b")
SECRET_RE = re.compile(
    r'(?:secret|password|api_key|token|passwd)\s*=\s*["\'][a-zA-Z0-9_\-]{16,}["\']',
    re.IGNORECASE,
)
_REQUIREMENT_SPEC_RE = re.compile(
    r"^([A-Za-z0-9][A-Za-z0-9._-]*)\s*(.*)$"
)
BINARY_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".pyc",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".zip",
        ".exe",
        ".dll",
        ".so",
        ".dylib",
        ".woff",
        ".woff2",
        ".ico",
        ".pdf",
        ".db",
    }
)
DEFAULT_IGNORE_DIRS: frozenset[str] = frozenset(
    {
        ".git",
        "__pycache__",
        "build",
        "dist",
    }
)
BLACKLIST_DIR_NAMES: frozenset[str] = frozenset(
    {
        "node_modules",
        "bower_components",
        "staticfiles",
        "venv",
        ".venv",
        "env",
        "site-packages",
        ".next",
        ".turbo",
    }
)
BLACKLIST_PATH_FRAGMENTS: tuple[str, ...] = (
    "node_modules/",
    "bower_components/",
    "staticfiles/",
    "static/vendor/",
    "assets/vendor/",
    "site-packages/",
    "venv/",
    ".venv/",
    "env/",
    ".next/",
    ".turbo/",
)
MANIFEST_JSON_FILES: frozenset[str] = frozenset(
    {
        "package.json",
        "composer.json",
        "package-lock.json",
    }
)
SKIP_EXTENSIONS: frozenset[str] = frozenset({".map", ".md"})
SKIP_NAME_SUFFIXES: tuple[str, ...] = (".min.js", ".min.css")
IGNORE_FILES: tuple[str, ...] = (".gitignore", ".cursorignore")


class MarkerFinding(TypedDict):
    file: str
    line: int
    marker: str


class SecretFinding(TypedDict):
    file: str
    line: int


class DependencyConflict(TypedDict):
    package: str
    versions: list[str]


class RiskReport(TypedDict):
    missing_tests: bool
    markers: list[MarkerFinding]
    secrets: list[SecretFinding]
    dependency_conflicts: list[DependencyConflict]


class RisksParser:
    def __init__(self, repo_path: str, dependencies: list[str] | None = None) -> None:
        self._repo_path = Path(repo_path)
        self._dependencies = dependencies
        self._ignore_patterns = self._load_ignore_patterns()

    def parse(self) -> RiskReport:
        markers: list[MarkerFinding] = []
        secrets: list[SecretFinding] = []

        for file_path in self._iter_text_files():
            file_markers, file_secrets = self._scan_file(file_path)
            markers.extend(file_markers)
            secrets.extend(file_secrets)

        return {
            "missing_tests": not self._has_test_directory(),
            "markers": markers,
            "secrets": secrets,
            "dependency_conflicts": self._check_dependency_conflicts(),
        }

    def _has_test_directory(self) -> bool:
        return any((self._repo_path / name).is_dir() for name in TEST_DIRS)

    def _load_ignore_patterns(self) -> list[str]:
        patterns: list[str] = []

        for ignore_file in IGNORE_FILES:
            path = self._repo_path / ignore_file
            if not path.is_file():
                continue

            try:
                lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
            except OSError:
                continue

            for line in lines:
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                patterns.append(stripped)

        return patterns

    def _is_ignored(self, relative: str, is_dir: bool) -> bool:
        normalized = relative.replace("\\", "/")

        for pattern in self._ignore_patterns:
            if pattern.endswith("/"):
                if is_dir and (
                    normalized == pattern[:-1]
                    or normalized.startswith(f"{pattern}")
                    or normalized.startswith(pattern[:-1] + "/")
                ):
                    return True
                continue

            if fnmatch.fnmatch(normalized, pattern):
                return True
            if fnmatch.fnmatch(Path(normalized).name, pattern):
                return True

        return False

    def _normalize_relative(self, path: str) -> str:
        return path.replace("\\", "/")

    def _is_blacklisted_path(self, relative: str) -> bool:
        normalized = self._normalize_relative(relative)
        parts = [part for part in normalized.split("/") if part]

        if any(part in BLACKLIST_DIR_NAMES for part in parts):
            return True

        prefixed = f"{normalized}/" if normalized else ""
        return any(fragment in prefixed for fragment in BLACKLIST_PATH_FRAGMENTS)

    def _is_skippable_file(self, relative: str, filename: str) -> bool:
        if self._is_blacklisted_path(relative):
            return True

        lowered_name = filename.lower()
        if any(lowered_name.endswith(suffix) for suffix in SKIP_NAME_SUFFIXES):
            return True

        suffix = Path(filename).suffix.lower()
        if suffix in SKIP_EXTENSIONS:
            return True

        if suffix == ".json" and filename not in MANIFEST_JSON_FILES:
            return True

        return False

    def _iter_text_files(self) -> Iterator[Path]:
        for root, dirs, files in os.walk(self._repo_path):
            root_path = Path(root)
            relative_root = root_path.relative_to(self._repo_path).as_posix()
            if relative_root == ".":
                relative_root = ""

            dirs[:] = sorted(
                directory
                for directory in dirs
                if directory not in DEFAULT_IGNORE_DIRS
                and directory not in BLACKLIST_DIR_NAMES
                and not self._is_ignored(
                    f"{relative_root}/{directory}".strip("/"),
                    is_dir=True,
                )
            )

            for filename in sorted(files):
                file_path = root_path / filename
                relative_file = file_path.relative_to(self._repo_path).as_posix()

                if self._is_ignored(relative_file, is_dir=False):
                    continue
                if self._is_skippable_file(relative_file, filename):
                    continue
                if self._is_binary(file_path):
                    continue

                yield file_path

    def _is_binary(self, path: Path) -> bool:
        if path.suffix.lower() in BINARY_EXTENSIONS:
            return True

        try:
            with path.open("rb") as handle:
                chunk = handle.read(8192)
        except OSError:
            return True

        return b"\x00" in chunk

    def _scan_file(
        self, path: Path
    ) -> tuple[list[MarkerFinding], list[SecretFinding]]:
        relative = path.relative_to(self._repo_path).as_posix()
        markers: list[MarkerFinding] = []
        secrets: list[SecretFinding] = []

        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            return markers, secrets

        for line_number, line in enumerate(lines, start=1):
            marker_match = MARKER_RE.search(line)
            if marker_match:
                markers.append(
                    {
                        "file": relative,
                        "line": line_number,
                        "marker": marker_match.group(1),
                    }
                )

            if SECRET_RE.search(line):
                secrets.append({"file": relative, "line": line_number})

        return markers, secrets

    def _check_dependency_conflicts(self) -> list[DependencyConflict]:
        if self._dependencies is not None and not self._has_dependency_manifests():
            return []

        conflicts: list[DependencyConflict] = []
        conflicts.extend(self._check_requirements_conflicts())
        conflicts.extend(self._check_package_json_conflicts())
        return sorted(conflicts, key=lambda item: item["package"])

    def _has_dependency_manifests(self) -> bool:
        return (self._repo_path / "requirements.txt").is_file() or (
            self._repo_path / "package.json"
        ).is_file()

    def _check_requirements_conflicts(self) -> list[DependencyConflict]:
        path = self._repo_path / "requirements.txt"
        if not path.is_file():
            return []

        versions_by_package: dict[str, set[str]] = defaultdict(set)

        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            return []

        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if stripped.startswith(("-r", "--requirement", "-e", "--editable")):
                continue

            match = _REQUIREMENT_SPEC_RE.match(stripped)
            if not match:
                continue

            package = match.group(1).lower()
            spec = match.group(2).strip() or "*"
            versions_by_package[package].add(spec)

        return self._build_conflicts(versions_by_package)

    def _check_package_json_conflicts(self) -> list[DependencyConflict]:
        path = self._repo_path / "package.json"
        if not path.is_file():
            return []

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []

        versions_by_package: dict[str, set[str]] = defaultdict(set)

        for key in ("dependencies", "devDependencies"):
            section = data.get(key)
            if not isinstance(section, dict):
                continue

            for package, version in section.items():
                if isinstance(version, str):
                    versions_by_package[package.lower()].add(version)

        return self._build_conflicts(versions_by_package)

    def _build_conflicts(
        self, versions_by_package: dict[str, set[str]]
    ) -> list[DependencyConflict]:
        conflicts: list[DependencyConflict] = []

        for package, versions in versions_by_package.items():
            if len(versions) > 1:
                conflicts.append(
                    {
                        "package": package,
                        "versions": sorted(versions),
                    }
                )

        return conflicts
