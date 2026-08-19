from __future__ import annotations

import os
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from rebrief.core.confidence import Confidence
from rebrief.core.ignore import IgnoreMatcher
from rebrief.plugins.base import PluginScanSettings, ScanContext
from rebrief.plugins.builtin._helpers import (
    BINARY_EXTENSIONS,
    MANIFEST_JSON_FILES,
    SKIP_EXTENSIONS,
    SKIP_NAME_SUFFIXES,
)

if TYPE_CHECKING:
    import re

    from rebrief.core.config import SecretPatternConfig
    from rebrief.parsers.git_log import GitLogResult
    from rebrief.parsers.ownership import OwnershipResult
    from rebrief.parsers.stack import StackResult


def _is_skippable_file(
    relative: str,
    filename: str,
    ignore_matcher: IgnoreMatcher,
) -> bool:
    if ignore_matcher.is_ignored(relative, is_dir=False):
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


def _is_binary(path: Path) -> bool:
    if path.suffix.lower() in BINARY_EXTENSIONS:
        return True

    try:
        with path.open("rb") as handle:
            chunk = handle.read(8192)
    except OSError:
        return True

    return b"\x00" in chunk


def iter_text_files(
    repo_path: Path,
    *,
    paths: Sequence[str] | None,
    extra_ignore_patterns: Sequence[str],
) -> Iterator[Path]:
    ignore_matcher = IgnoreMatcher(str(repo_path), extra_patterns=extra_ignore_patterns)
    path_set = (
        {path.replace("\\", "/") for path in paths} if paths is not None else None
    )

    if path_set is not None:
        for relative in sorted(path_set):
            file_path = repo_path / relative
            if not file_path.is_file():
                continue
            if _is_skippable_file(relative, file_path.name, ignore_matcher):
                continue
            if _is_binary(file_path):
                continue
            yield file_path
        return

    for root, dirs, files in os.walk(repo_path):
        root_path = Path(root)
        relative_root = root_path.relative_to(repo_path).as_posix()
        if relative_root == ".":
            relative_root = ""

        dirs[:] = sorted(
            directory
            for directory in dirs
            if not ignore_matcher.should_prune_dir(directory, relative_root)
        )

        for filename in sorted(files):
            file_path = root_path / filename
            relative_file = file_path.relative_to(repo_path).as_posix()

            if ignore_matcher.is_ignored(relative_file, is_dir=False):
                continue
            if _is_skippable_file(relative_file, filename, ignore_matcher):
                continue
            if _is_binary(file_path):
                continue

            yield file_path


def _pattern_pairs(
    custom_secret_patterns: tuple[SecretPatternConfig, ...] | None,
) -> tuple[tuple[re.Pattern[str], Confidence], ...]:
    if not custom_secret_patterns:
        return ()
    return tuple((pattern.regex, pattern.confidence) for pattern in custom_secret_patterns)


def build_scan_context(
    repo_path: str | Path,
    *,
    stack: StackResult,
    git_log: GitLogResult,
    ownership: OwnershipResult,
    paths: Sequence[str] | None = None,
    entropy_cutoff: float,
    extra_ignore_patterns: Sequence[str] = (),
    custom_secret_patterns: tuple[SecretPatternConfig, ...] | None = None,
    min_confidence: str = "medium",
) -> ScanContext:
    resolved_paths = (
        tuple(path.replace("\\", "/") for path in paths) if paths is not None else None
    )
    return ScanContext(
        repo_path=Path(repo_path).resolve(),
        stack=stack,
        git_log=git_log,
        ownership=ownership,
        paths=resolved_paths,
        settings=PluginScanSettings(
            entropy_cutoff=entropy_cutoff,
            extra_ignore_patterns=tuple(extra_ignore_patterns),
            custom_secret_patterns=_pattern_pairs(custom_secret_patterns),
            min_confidence=min_confidence,
        ),
    )
