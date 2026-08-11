from __future__ import annotations

import json
import math
import os
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterator, TypedDict

from rebrief.core.confidence import Confidence
from rebrief.core.ignore import IgnoreMatcher

TEST_DIRS: tuple[str, ...] = ("tests", "test", "__tests__")
MARKER_RE = re.compile(r"\b(TODO|FIXME|HACK|BUG)\b")

# Secret detection requires BOTH signals:
# 1. Variable/kwarg name semantically implies a credential (word-exact match).
# 2. Value matches a known secret format OR has high entropy (20+ chars, no code-like chars).
ENTROPY_MIN_LENGTH = 20
ENTROPY_THRESHOLD = 3.5

CREDENTIAL_NAME_WORDS: frozenset[str] = frozenset({
    "key",
    "secret",
    "token",
    "password",
    "passwd",
    "credential",
    "credentials",
    "auth",
    "bearer",
})
_CAMEL_BOUNDARY_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")

EXCLUDED_ATTRIBUTE_NAMES: frozenset[str] = frozenset(
    {"classname", "class", "style", "d"}
)
EXCLUDED_NAME_SUFFIXES: tuple[str, ...] = ("path", "pathdata")
MIGRATION_FIELD_NAMES: frozenset[str] = frozenset({
    "revision",
    "down_revision",
    "branch_labels",
    "depends_on",
})
MIGRATION_PATH_FRAGMENTS: tuple[str, ...] = ("alembic/versions/", "migrations/")

KNOWN_SECRET_FORMAT_RE = re.compile(
    r"AKIA[0-9A-Z]{16}"  # AWS access key ID
    r"|sk-[a-zA-Z0-9_\-]{20,}"  # OpenAI / similar sk- prefixed keys
    r"|gh[pos]_[A-Za-z0-9]{36,}"  # GitHub personal/OAuth/server tokens
    r"|github_pat_[A-Za-z0-9_]{20,}"  # GitHub fine-grained PAT
    r"|AIza[0-9A-Za-z_\-]{35}"  # Google API key
    r"|xox[baprs]-[A-Za-z0-9-]+"  # Slack tokens
    r"|eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]*"  # JWT
)
FORBIDDEN_LITERAL_CHARS_RE = re.compile(r"[\s.\[\]()/]")
_NAMESPACE_STORAGE_KEY_RE = re.compile(r"^[a-z0-9]+(:[a-z0-9-]+)+$")
_LOWERCASE_IDENTIFIER_CHARS_RE = re.compile(r"^[a-z0-9:-]+$")

_QUOTED_ASSIGNMENT_RE = re.compile(
    r"(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*"
    r"(?P<prefix>[a-zA-Z]{0,2})"
    r'(?P<quote>"""|\'\'\'|"|\')'
    r"(?P<value>.*?)"
    r"(?P=quote)"
)
_ENV_STYLE_ASSIGNMENT_RE = re.compile(
    r"^\s*(?:export\s+)?(?P<name>[A-Z_][A-Z0-9_]*)\s*=\s*(?P<value>[^\s#'\"]+)\s*(?:#.*)?$"
)
_REQUIREMENT_SPEC_RE = re.compile(
    r"^([A-Za-z0-9][A-Za-z0-9._-]*)\s*(.*)$"
)


def _shannon_entropy(value: str) -> float:
    if not value:
        return 0.0
    length = len(value)
    return -sum(
        (count / length) * math.log2(count / length)
        for count in Counter(value).values()
    )


def _identifier_words(name: str) -> list[str]:
    normalized = _CAMEL_BOUNDARY_RE.sub("_", name.replace("-", "_"))
    return [word.lower() for word in normalized.split("_") if word]


def _name_implies_credential(name: str) -> bool:
    return any(word in CREDENTIAL_NAME_WORDS for word in _identifier_words(name))


def _is_migration_path(relative_path: str) -> bool:
    normalized = relative_path.replace("\\", "/")
    prefixed = f"{normalized}/" if normalized else ""
    return any(fragment in prefixed for fragment in MIGRATION_PATH_FRAGMENTS)


def _is_excluded_context(relative_path: str, name: str) -> bool:
    lowered = name.lower()
    if lowered in EXCLUDED_ATTRIBUTE_NAMES:
        return True
    if lowered.endswith(EXCLUDED_NAME_SUFFIXES):
        return True
    if lowered in MIGRATION_FIELD_NAMES and _is_migration_path(relative_path):
        return True
    return False


def _iter_literal_candidates(line: str) -> Iterator[tuple[str, str]]:
    for match in _QUOTED_ASSIGNMENT_RE.finditer(line):
        prefix = match.group("prefix").lower()
        value = match.group("value")
        if "f" in prefix and "{" in value:
            continue  # f-string with interpolation, not a static literal
        yield match.group("name"), value

    env_match = _ENV_STYLE_ASSIGNMENT_RE.match(line)
    if env_match:
        yield env_match.group("name"), env_match.group("value")


def _is_namespaced_storage_key(value: str) -> bool:
    if _NAMESPACE_STORAGE_KEY_RE.match(value):
        return True
    if ":" not in value:
        return False
    return _LOWERCASE_IDENTIFIER_CHARS_RE.match(value) is not None


def _classify_secret_value(value: str) -> Confidence | None:
    if KNOWN_SECRET_FORMAT_RE.search(value):
        return Confidence.HIGH
    if _is_namespaced_storage_key(value):
        return None
    if len(value) < ENTROPY_MIN_LENGTH:
        return None
    if FORBIDDEN_LITERAL_CHARS_RE.search(value):
        return None
    if _shannon_entropy(value) >= ENTROPY_THRESHOLD:
        return Confidence.MEDIUM
    return None


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
MANIFEST_JSON_FILES: frozenset[str] = frozenset(
    {
        "package.json",
        "composer.json",
        "package-lock.json",
    }
)
SKIP_EXTENSIONS: frozenset[str] = frozenset({".map", ".md"})
SKIP_NAME_SUFFIXES: tuple[str, ...] = (".min.js", ".min.css")


class MarkerFinding(TypedDict):
    file: str
    line: int
    marker: str
    confidence: str


class SecretFinding(TypedDict):
    file: str
    line: int
    confidence: str


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
        self._ignore_matcher = IgnoreMatcher(repo_path)

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

    def _is_skippable_file(self, relative: str, filename: str) -> bool:
        if self._ignore_matcher.is_ignored(relative, is_dir=False):
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
                if not self._ignore_matcher.should_prune_dir(directory, relative_root)
            )

            for filename in sorted(files):
                file_path = root_path / filename
                relative_file = file_path.relative_to(self._repo_path).as_posix()

                if self._ignore_matcher.is_ignored(relative_file, is_dir=False):
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
        is_csv = Path(relative).suffix.lower() == ".csv"
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
                        "confidence": Confidence.LOW.value,
                    }
                )

            if not is_csv:
                secret_confidence = self._line_secret_confidence(line, relative)
                if secret_confidence is not None:
                    secrets.append(
                        {
                            "file": relative,
                            "line": line_number,
                            "confidence": secret_confidence.value,
                        }
                    )

        return markers, secrets

    def _line_secret_confidence(
        self, line: str, relative_path: str
    ) -> Confidence | None:
        best: Confidence | None = None
        for name, value in _iter_literal_candidates(line):
            if _is_excluded_context(relative_path, name):
                continue
            if not _name_implies_credential(name):
                continue
            confidence = _classify_secret_value(value)
            if confidence is None:
                continue
            if confidence == Confidence.HIGH:
                return Confidence.HIGH
            best = confidence
        return best

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
