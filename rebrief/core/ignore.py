from __future__ import annotations

import fnmatch
from collections.abc import Sequence
from pathlib import Path

REBRIEFIGNORE_FILENAME = ".rebriefignore"

DEFAULT_IGNORE_DIRS: frozenset[str] = frozenset(
    {
        ".git",
        ".next",
        ".rebrief",
        ".turbo",
        ".venv",
        "__pycache__",
        "bower_components",
        "build",
        "dist",
        "env",
        "node_modules",
        "site-packages",
        "staticfiles",
        "venv",
    }
)

DEFAULT_IGNORE_PATTERNS: tuple[str, ...] = (
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
    ".rebrief/",
    ".turbo/",
)

SUPPLEMENTAL_IGNORE_FILES: tuple[str, ...] = (
    ".rebriefignore",
    ".gitignore",
    ".cursorignore",
)

DEFAULT_REBRIEFIGNORE_CONTENT = """\
# Dependencies and package managers
node_modules/
vendor/

# Build outputs
dist/
build/
.next/
.turbo/

# Python
__pycache__/
.venv/
venv/

# Version control
.git/

# Rebrief cache
.rebrief/
"""


def parse_ignore_lines(text: str) -> list[str]:
    patterns: list[str] = []

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        patterns.append(stripped)

    return patterns


def ensure_rebriefignore(repo_path: Path) -> bool:
    """Create a default .rebriefignore if missing. Returns True if created."""
    target = repo_path / REBRIEFIGNORE_FILENAME
    if target.is_file():
        return False

    try:
        target.write_text(DEFAULT_REBRIEFIGNORE_CONTENT, encoding="utf-8")
    except OSError as exc:
        raise OSError(
            f"Failed to create {REBRIEFIGNORE_FILENAME} in {repo_path}: {exc}"
        ) from exc

    return True


class IgnoreMatcher:
    def __init__(
        self,
        repo_path: str | Path,
        extra_patterns: Sequence[str] = (),
    ) -> None:
        self._repo_path = Path(repo_path)
        self._supplemental_patterns = self._load_supplemental_patterns()
        if extra_patterns:
            self._supplemental_patterns.extend(extra_patterns)

    def _load_supplemental_patterns(self) -> list[str]:
        patterns: list[str] = []

        for ignore_file in SUPPLEMENTAL_IGNORE_FILES:
            path = self._repo_path / ignore_file
            if not path.is_file():
                continue

            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue

            patterns.extend(parse_ignore_lines(text))

        return patterns

    def _normalize_relative(self, path: str) -> str:
        return path.replace("\\", "/")

    def _matches_default_dirs(self, relative: str) -> bool:
        normalized = self._normalize_relative(relative)
        parts = [part for part in normalized.split("/") if part]
        return any(part in DEFAULT_IGNORE_DIRS for part in parts)

    def _matches_default_patterns(self, relative: str) -> bool:
        normalized = self._normalize_relative(relative)
        prefixed = f"{normalized}/" if normalized else ""
        return any(fragment in prefixed for fragment in DEFAULT_IGNORE_PATTERNS)

    def _matches_supplemental_pattern(self, relative: str, *, is_dir: bool) -> bool:
        normalized = self._normalize_relative(relative)

        for pattern in self._supplemental_patterns:
            if pattern.endswith("/"):
                dir_name = pattern[:-1]
                if is_dir:
                    if (
                        normalized == dir_name
                        or normalized.endswith(f"/{dir_name}")
                    ):
                        return True
                else:
                    if normalized.startswith(f"{dir_name}/") or f"/{dir_name}/" in normalized:
                        return True
                continue

            if fnmatch.fnmatch(normalized, pattern):
                return True
            if fnmatch.fnmatch(Path(normalized).name, pattern):
                return True

        return False

    def is_ignored(self, relative: str, *, is_dir: bool) -> bool:
        if self._matches_default_dirs(relative):
            return True
        if self._matches_default_patterns(relative):
            return True
        return self._matches_supplemental_pattern(relative, is_dir=is_dir)

    def should_prune_dir(self, dir_name: str, parent_relative: str) -> bool:
        relative = f"{parent_relative}/{dir_name}".strip("/")
        return self.is_ignored(relative, is_dir=True)
