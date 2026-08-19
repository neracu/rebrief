from __future__ import annotations

import fnmatch
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict


class WorkspaceMember(TypedDict):
    name: str
    path: str
    source: str
    git_root: str | None
    path_prefix: str | None


@dataclass(frozen=True)
class ResolvedTarget:
    root: Path
    source: str
    is_remote: bool


def _normalize_pattern(pattern: str) -> str:
    return pattern.strip().strip('"').strip("'").replace("\\", "/")


def _expand_glob(root: Path, pattern: str) -> list[Path]:
    normalized = _normalize_pattern(pattern)
    if not normalized:
        return []

    if "*" in normalized or "?" in normalized or "[" in normalized:
        matches = sorted(root.glob(normalized))
        return [
            match
            for match in matches
            if match.is_dir() and match.name != "node_modules"
        ]

    candidate = (root / normalized).resolve()
    if candidate.is_dir():
        return [candidate]
    return []


def _dedupe_members(members: list[WorkspaceMember]) -> list[WorkspaceMember]:
    seen: set[str] = set()
    result: list[WorkspaceMember] = []
    for member in members:
        key = str(Path(member["path"]).resolve())
        if key in seen:
            continue
        seen.add(key)
        result.append(member)
    return result


def _member_from_path(
    member_path: Path,
    *,
    source: str,
    git_root: Path | None,
) -> WorkspaceMember:
    resolved = member_path.resolve()
    prefix: str | None = None
    if git_root is not None:
        try:
            prefix = resolved.relative_to(git_root.resolve()).as_posix()
            if prefix != "":
                prefix = f"{prefix}/"
            else:
                prefix = None
        except ValueError:
            prefix = None

    return {
        "name": resolved.name or source,
        "path": str(resolved),
        "source": source,
        "git_root": str(git_root.resolve()) if git_root is not None else None,
        "path_prefix": prefix,
    }


def _parse_pnpm_workspace(root: Path) -> list[str] | None:
    for filename in ("pnpm-workspace.yaml", "pnpm-workspace.yml"):
        path = root / filename
        if not path.is_file():
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except OSError:
            continue

        patterns: list[str] = []
        in_packages = False
        for line in content.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if stripped == "packages:":
                in_packages = True
                continue
            if in_packages:
                if not stripped.startswith("- "):
                    if ":" in stripped and not stripped.startswith("-"):
                        break
                    continue
                entry = _normalize_pattern(stripped[2:].strip())
                if entry.startswith("!"):
                    continue
                patterns.append(entry)
        if patterns:
            return patterns
    return None


def _parse_lerna_workspace(root: Path) -> list[str] | None:
    path = root / "lerna.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    packages = data.get("packages")
    if isinstance(packages, list):
        return [_normalize_pattern(str(item)) for item in packages if str(item).strip()]
    return None


def _parse_npm_workspaces(root: Path) -> list[str] | None:
    path = root / "package.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    workspaces = data.get("workspaces")
    if isinstance(workspaces, list):
        return [_normalize_pattern(str(item)) for item in workspaces if str(item).strip()]
    if isinstance(workspaces, dict):
        packages = workspaces.get("packages")
        if isinstance(packages, list):
            return [
                _normalize_pattern(str(item)) for item in packages if str(item).strip()
            ]
    return None


def _parse_cargo_workspace_members(root: Path) -> list[str] | None:
    path = root / "Cargo.toml"
    if not path.is_file():
        return None
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return None

    if sys.version_info >= (3, 11):
        import tomllib

        try:
            data = tomllib.loads(content)
        except tomllib.TOMLDecodeError:
            return None
        workspace = data.get("workspace")
        if not isinstance(workspace, dict):
            return None
        members = workspace.get("members")
        if not isinstance(members, list):
            return None
        exclude = workspace.get("exclude")
        excluded: set[str] = set()
        if isinstance(exclude, list):
            excluded = {_normalize_pattern(str(item)) for item in exclude}
        patterns = [
            _normalize_pattern(str(item))
            for item in members
            if str(item).strip()
        ]
        return [pattern for pattern in patterns if pattern not in excluded]

    return _parse_cargo_workspace_regex(content)


def _parse_cargo_workspace_regex(content: str) -> list[str] | None:
    in_workspace = False
    members: list[str] = []
    exclude: set[str] = set()

    for line in content.splitlines():
        stripped = line.strip()
        if stripped == "[workspace]":
            in_workspace = True
            continue
        if stripped.startswith("[") and stripped != "[workspace]":
            in_workspace = False
            continue
        if not in_workspace:
            continue

        member_match = re.match(r'members\s*=\s*\[(.*)\]', stripped)
        if member_match:
            inner = member_match.group(1)
            members.extend(
                _normalize_pattern(item)
                for item in re.findall(r'"([^"]+)"', inner)
            )
            continue

        exclude_match = re.match(r'exclude\s*=\s*\[(.*)\]', stripped)
        if exclude_match:
            inner = exclude_match.group(1)
            exclude.update(
                _normalize_pattern(item) for item in re.findall(r'"([^"]+)"', inner)
            )

    if not members:
        return None
    return [pattern for pattern in members if pattern not in exclude]


def detect_workspace_patterns(root: Path) -> list[str] | None:
    """Return workspace member glob patterns, or None if not a workspace root."""
    for parser in (
        _parse_pnpm_workspace,
        _parse_lerna_workspace,
        _parse_npm_workspaces,
        _parse_cargo_workspace_members,
    ):
        patterns = parser(root)
        if patterns:
            return patterns
    return None


def expand_workspace_members(
    root: Path,
    *,
    source: str,
) -> list[WorkspaceMember]:
    """Expand a target root into workspace members or a single member."""
    resolved_root = root.resolve()
    git_root = resolved_root if (resolved_root / ".git").exists() else None
    patterns = detect_workspace_patterns(resolved_root)

    if patterns is None:
        return [_member_from_path(resolved_root, source=source, git_root=git_root)]

    members: list[WorkspaceMember] = []
    for pattern in patterns:
        for member_path in _expand_glob(resolved_root, pattern):
            members.append(
                _member_from_path(member_path, source=source, git_root=git_root)
            )

    if not members:
        return [_member_from_path(resolved_root, source=source, git_root=git_root)]

    return _dedupe_members(members)


def path_matches_prefix(path: str, prefix: str | None) -> bool:
    """True when ``path`` is under the workspace member prefix."""
    if prefix is None:
        return True
    normalized = path.replace("\\", "/")
    if prefix == "":
        return True
    if prefix.endswith("/"):
        return normalized.startswith(prefix) or normalized == prefix.rstrip("/")
    return normalized.startswith(f"{prefix}/") or normalized == prefix


def filter_paths_by_prefix(paths: list[str], prefix: str | None) -> list[str]:
    if prefix is None:
        return paths
    return [path for path in paths if path_matches_prefix(path, prefix)]


def glob_matches_any(path: str, patterns: list[str]) -> bool:
    normalized = path.replace("\\", "/")
    return any(fnmatch.fnmatch(normalized, pattern) for pattern in patterns)
