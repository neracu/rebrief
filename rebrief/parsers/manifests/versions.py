from __future__ import annotations

import re
from typing import TypedDict


class PackageSpec(TypedDict):
    name: str
    version: str
    ecosystem: str
    exact: bool
    spec: str


_SKIP_VERSION_PREFIXES = ("workspace:", "file:", "link:", "git+", "github:", "npm:")
_SKIP_VERSIONS = frozenset({"*", "latest", "x", "X"})


def _normalize_version(version: str) -> str:
    return version.lstrip("vV")


def _is_skippable_version(spec: str) -> bool:
    stripped = spec.strip()
    if not stripped or stripped in _SKIP_VERSIONS:
        return True
    lowered = stripped.lower()
    return any(lowered.startswith(prefix) for prefix in _SKIP_VERSION_PREFIXES)


def parse_npm_version(name: str, spec: str) -> PackageSpec | None:
    if not isinstance(spec, str) or _is_skippable_version(spec):
        return None

    stripped = spec.strip()
    exact = False
    version = stripped

    if stripped.startswith("^") or stripped.startswith("~"):
        version = stripped[1:]
        exact = False
    elif stripped.startswith(">="):
        version = stripped[2:].strip()
        exact = False
    elif stripped.startswith(">"):
        version = stripped[1:].strip()
        exact = False
    elif re.match(r"^\d", stripped):
        exact = True
    else:
        return None

    version = _normalize_version(version)
    if not version or _is_skippable_version(version):
        return None

    return {
        "name": name,
        "version": version,
        "ecosystem": "npm",
        "exact": exact,
        "spec": stripped,
    }


_PEP508_NAME_RE = re.compile(
    r"^([A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?)"
)
_PEP508_SPEC_RE = re.compile(
    r"(?:==|>=|<=|>|<|!=|~=)\s*([^\s,;]+)"
)


def parse_pypi_spec(spec: str) -> PackageSpec | None:
    stripped = spec.strip()
    if not stripped:
        return None

    name_match = _PEP508_NAME_RE.match(stripped)
    if not name_match:
        return None

    name = name_match.group(1)
    remainder = stripped[name_match.end() :].strip()

    if not remainder:
        return None

    if remainder.startswith("==") or remainder.startswith("="):
        version_match = re.match(r"==?\s*([^\s,;]+)", remainder)
        if version_match:
            version = _normalize_version(version_match.group(1))
            if version:
                return {
                    "name": name,
                    "version": version,
                    "ecosystem": "PyPI",
                    "exact": True,
                    "spec": stripped,
                }
        return None

    if remainder.startswith(">="):
        version_match = re.match(r">=\s*([^\s,;]+)", remainder)
        if version_match:
            version = _normalize_version(version_match.group(1))
            if version:
                return {
                    "name": name,
                    "version": version,
                    "ecosystem": "PyPI",
                    "exact": False,
                    "spec": stripped,
                }
        return None

    # Try other specifiers as lower bound
    spec_match = _PEP508_SPEC_RE.search(remainder)
    if spec_match:
        version = _normalize_version(spec_match.group(1))
        if version:
            return {
                "name": name,
                "version": version,
                "ecosystem": "PyPI",
                "exact": False,
                "spec": stripped,
            }

    return None


def parse_go_module(name: str, version: str) -> PackageSpec | None:
    if not name or not version:
        return None
    normalized = _normalize_version(version)
    if not normalized or normalized in _SKIP_VERSIONS:
        return None
    return {
        "name": name,
        "version": normalized,
        "ecosystem": "Go",
        "exact": True,
        "spec": f"{name} {version}",
    }


def parse_cargo_version(name: str, spec: str) -> PackageSpec | None:
    if not name or not spec:
        return None

    stripped = spec.strip()
    if stripped.startswith("{"):
        version_match = re.search(r'version\s*=\s*"([^"]+)"', stripped)
        if not version_match:
            return None
        version = version_match.group(1)
    else:
        version = stripped.strip('"')

    normalized = _normalize_version(version)
    if not normalized:
        return None

    # Cargo version strings like "1.0" are caret ranges.
    exact = bool(re.match(r"^\d+\.\d+\.\d+", normalized))
    return {
        "name": name,
        "version": normalized,
        "ecosystem": "crates.io",
        "exact": exact,
        "spec": stripped,
    }


def parse_composer_version(name: str, spec: str) -> PackageSpec | None:
    if not name or not isinstance(spec, str):
        return None
    lowered = name.lower()
    if lowered == "php" or lowered.startswith("ext-"):
        return None
    if _is_skippable_version(spec):
        return None

    stripped = spec.strip()
    exact = False
    version = stripped

    if stripped.startswith("^") or stripped.startswith("~"):
        version = stripped[1:]
        exact = False
    elif stripped.startswith(">="):
        version = stripped[2:].strip()
        exact = False
    elif re.match(r"^\d", stripped):
        exact = True
    else:
        return None

    version = _normalize_version(version)
    if not version:
        return None

    return {
        "name": name,
        "version": version,
        "ecosystem": "Packagist",
        "exact": exact,
        "spec": stripped,
    }


def parse_maven_coord(group: str, artifact: str, version: str) -> PackageSpec | None:
    if not group or not artifact or not version:
        return None
    if version.startswith("${"):
        return None
    normalized = _normalize_version(version.strip())
    if not normalized:
        return None
    name = f"{group}:{artifact}"
    return {
        "name": name,
        "version": normalized,
        "ecosystem": "Maven",
        "exact": True,
        "spec": f"{name}:{version}",
    }


def parse_gradle_coord(coord: str) -> PackageSpec | None:
    parts = coord.split(":")
    if len(parts) < 3:
        return None
    group, artifact, version = parts[0], parts[1], parts[2]
    return parse_maven_coord(group, artifact, version)


def parse_gem_version(name: str, version: str) -> PackageSpec | None:
    if not name or not version:
        return None
    normalized = _normalize_version(version.strip().strip("'\""))
    if not normalized:
        return None
    return {
        "name": name,
        "version": normalized,
        "ecosystem": "RubyGems",
        "exact": True,
        "spec": f"{name} {version}",
    }
