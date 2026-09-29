from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Literal, NotRequired, TypedDict

from rebrief.core.confidence import Confidence

TEST_DIRS: tuple[str, ...] = ("tests", "test", "__tests__")
TEST_PATH_SEGMENTS: frozenset[str] = frozenset(
    {"tests", "test", "__tests__", "spec", "fixtures"}
)
MARKER_RE = re.compile(r"\b(TODO|FIXME|HACK|BUG)\b")


def is_test_or_fixture_path(relative_path: str) -> bool:
    """True when any path segment is an exact test/fixture directory name."""
    parts = [
        part.lower()
        for part in relative_path.replace("\\", "/").split("/")
        if part
    ]
    return any(part in TEST_PATH_SEGMENTS for part in parts)

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
    r"AKIA[0-9A-Z]{16}"
    r"|sk-[a-zA-Z0-9_\-]{20,}"
    r"|gh[pos]_[A-Za-z0-9]{36,}"
    r"|github_pat_[A-Za-z0-9_]{20,}"
    r"|AIza[0-9A-Za-z_\-]{35}"
    r"|xox[baprs]-[A-Za-z0-9-]+"
    r"|eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]*"
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
SECRET_SKIP_EXTENSIONS: frozenset[str] = frozenset({".map"})
SKIP_NAME_SUFFIXES: tuple[str, ...] = (".min.js", ".min.css")

EVM_PRIVATE_KEY_RE = re.compile(r"\b(0x)?[a-fA-F0-9]{64}\b")
KNOWN_EVM_TEST_PRIVATE_KEYS: frozenset[str] = frozenset(
    {
        "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80",
        "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d",
        "0x5de4111afa1a4b94908f83103eb1f1706367c2e68ca870fc3fb9a804cdab365a",
        "0x7c852118294e51e653712a81e05800f419141751be58f605c371e15141b007a6",
        "0x47e179ec197488593b187f80a00eb0da91f1b9d0b13f8733639f19c30a34926a",
        "0x8b3a350cf5c34c9194ca85829a2df0ec3153be0318b5e2d3348e872092edffba",
        "0x92db14e403b83dfe3df233f83dfa3a0d7096f21ca9b0d6d6b8d88b2b4ec1564e",
        "0x4bbbf85ce3377467afe5d46f804f221813b2bb87f24d81f60f1fcdbf7cbf4356",
        "0xdbda1821b80551c9d65939329250298aa3472ba22feea921c0cf5d620ea67b97",
        "0x2a871d0798f97d79848a013d4936a73bf4cc922c825d33c1cf7073dff6d409c6",
    }
)
SecretKind = Literal["default", "evm_public", "evm_private"]


class MarkerFinding(TypedDict):
    file: str
    line: int
    marker: str
    confidence: str


class SecretFinding(TypedDict):
    file: str
    line: int
    confidence: str
    kind: NotRequired[SecretKind]


class DependencyConflict(TypedDict):
    package: str
    versions: list[str]


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
            continue
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


def classify_secret_value(
    value: str,
    *,
    entropy_cutoff: float = ENTROPY_THRESHOLD,
    custom_patterns: Sequence[tuple[re.Pattern[str], Confidence]] = (),
) -> Confidence | None:
    for pattern, confidence in custom_patterns:
        if pattern.search(value):
            return confidence
    if KNOWN_SECRET_FORMAT_RE.search(value):
        return Confidence.HIGH
    if _is_namespaced_storage_key(value):
        return None
    if len(value) < ENTROPY_MIN_LENGTH:
        return None
    if FORBIDDEN_LITERAL_CHARS_RE.search(value):
        return None
    if _shannon_entropy(value) >= entropy_cutoff:
        return Confidence.MEDIUM
    return None


def line_secret_confidence(
    line: str,
    relative_path: str,
    *,
    entropy_cutoff: float = ENTROPY_THRESHOLD,
    custom_patterns: Sequence[tuple[re.Pattern[str], Confidence]] = (),
) -> Confidence | None:
    best: Confidence | None = None
    for name, value in _iter_literal_candidates(line):
        if _is_excluded_context(relative_path, name):
            continue
        if not _name_implies_credential(name):
            continue
        confidence = classify_secret_value(
            value,
            entropy_cutoff=entropy_cutoff,
            custom_patterns=custom_patterns,
        )
        if confidence is None:
            continue
        if confidence == Confidence.HIGH:
            return Confidence.HIGH
        best = confidence
    return best


def _normalize_evm_private_key(raw: str) -> str:
    lowered = raw.lower()
    if lowered.startswith("0x"):
        return lowered
    return f"0x{lowered}"


def find_evm_private_keys_on_line(line: str) -> list[tuple[str, bool]]:
    findings: list[tuple[str, bool]] = []
    for match in EVM_PRIVATE_KEY_RE.finditer(line):
        normalized = _normalize_evm_private_key(match.group(0))
        is_known = normalized in KNOWN_EVM_TEST_PRIVATE_KEYS
        findings.append((normalized, is_known))
    return findings


def _evm_secret_kind_on_line(line: str) -> SecretKind | None:
    matches = find_evm_private_keys_on_line(line)
    if not matches:
        return None
    if any(not is_known for _, is_known in matches):
        return "evm_private"
    return "evm_public"


def _secret_finding_for_line(
    relative: str,
    line_number: int,
    line: str,
    *,
    entropy_cutoff: float,
    custom_patterns: Sequence[tuple[re.Pattern[str], Confidence]],
) -> SecretFinding | None:
    evm_kind = _evm_secret_kind_on_line(line)
    credential_confidence = line_secret_confidence(
        line,
        relative,
        entropy_cutoff=entropy_cutoff,
        custom_patterns=custom_patterns,
    )

    if evm_kind == "evm_private":
        return {
            "file": relative,
            "line": line_number,
            "confidence": Confidence.HIGH.value,
            "kind": "evm_private",
        }
    if evm_kind == "evm_public":
        return {
            "file": relative,
            "line": line_number,
            "confidence": Confidence.HIGH.value,
            "kind": "evm_public",
        }
    if credential_confidence is not None:
        return {
            "file": relative,
            "line": line_number,
            "confidence": credential_confidence.value,
        }
    return None


def scan_file_markers_and_secrets(
    path: Path,
    repo_path: Path,
    *,
    entropy_cutoff: float,
    custom_patterns: Sequence[tuple[re.Pattern[str], Confidence]],
    scan_markers: bool = True,
    scan_secrets: bool = True,
) -> tuple[list[MarkerFinding], list[SecretFinding]]:
    relative = path.relative_to(repo_path).as_posix()
    is_csv = Path(relative).suffix.lower() == ".csv"
    markers: list[MarkerFinding] = []
    secrets: list[SecretFinding] = []

    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return markers, secrets

    for line_number, line in enumerate(lines, start=1):
        if scan_markers:
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

        if scan_secrets and not is_csv:
            finding = _secret_finding_for_line(
                relative,
                line_number,
                line,
                entropy_cutoff=entropy_cutoff,
                custom_patterns=custom_patterns,
            )
            if finding is not None:
                secrets.append(finding)

    return markers, secrets


def has_test_directory(repo_path: Path) -> bool:
    return any((repo_path / name).is_dir() for name in TEST_DIRS)


def check_dependency_conflicts(
    repo_path: Path,
    dependencies: list[str] | None,
    paths: set[str] | None,
) -> list[DependencyConflict]:
    if dependencies is not None and not _has_dependency_manifests(repo_path, paths):
        return []

    conflicts: list[DependencyConflict] = []
    if paths is None or "requirements.txt" in paths:
        conflicts.extend(_check_requirements_conflicts(repo_path))
    if paths is None or "package.json" in paths:
        conflicts.extend(_check_package_json_conflicts(repo_path))
    return sorted(conflicts, key=lambda item: item["package"])


def _has_dependency_manifests(repo_path: Path, paths: set[str] | None) -> bool:
    if paths is not None:
        return "requirements.txt" in paths or "package.json" in paths
    return (repo_path / "requirements.txt").is_file() or (
        repo_path / "package.json"
    ).is_file()


def _check_requirements_conflicts(repo_path: Path) -> list[DependencyConflict]:
    path = repo_path / "requirements.txt"
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

    return _build_conflicts(versions_by_package)


def _check_package_json_conflicts(repo_path: Path) -> list[DependencyConflict]:
    path = repo_path / "package.json"
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

    return _build_conflicts(versions_by_package)


def _build_conflicts(
    versions_by_package: dict[str, set[str]],
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


def secret_finding_to_risk_item(entry: SecretFinding) -> dict[str, str]:
    kind = entry.get("kind", "default")
    if kind == "evm_public":
        return {
            "severity": "warning",
            "message": (
                f"Hard-coded secret in {entry['file']}:{entry['line']} "
                "[Test / Public Anvil Key]"
            ),
            "confidence": entry["confidence"],
        }
    if kind == "evm_private":
        return {
            "severity": "critical",
            "message": f"Hard-coded secret in {entry['file']}:{entry['line']}",
            "confidence": entry["confidence"],
        }
    if is_test_or_fixture_path(entry["file"]):
        return {
            "severity": "warning",
            "message": (
                "Hard-coded secret-like value in test/example file "
                f"{entry['file']}:{entry['line']}"
            ),
            "confidence": entry["confidence"],
        }
    return {
        "severity": "critical",
        "message": f"Hard-coded secret in {entry['file']}:{entry['line']}",
        "confidence": entry["confidence"],
    }
