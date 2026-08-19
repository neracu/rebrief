from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path
from typing import TypedDict

from rebrief.core.confidence import Confidence
from rebrief.plugins.builtin._helpers import (
    ENTROPY_THRESHOLD,
    DependencyConflict,
    MarkerFinding,
    SecretFinding,
    check_dependency_conflicts,
    has_test_directory,
    is_test_or_fixture_path,
    line_secret_confidence,
    scan_file_markers_and_secrets,
)
from rebrief.plugins.context import iter_text_files

TEST_DIRS: tuple[str, ...] = ("tests", "test", "__tests__")
TEST_PATH_SEGMENTS: frozenset[str] = frozenset(
    {"tests", "test", "__tests__", "spec", "fixtures"}
)


class RiskReport(TypedDict):
    missing_tests: bool
    markers: list[MarkerFinding]
    secrets: list[SecretFinding]
    dependency_conflicts: list[DependencyConflict]


class RisksParser:
    def __init__(
        self,
        repo_path: str,
        dependencies: list[str] | None = None,
        paths: Sequence[str] | None = None,
        *,
        extra_ignore_patterns: Sequence[str] = (),
        entropy_cutoff: float = ENTROPY_THRESHOLD,
        custom_patterns: Sequence[tuple[re.Pattern[str], Confidence]] = (),
    ) -> None:
        self._repo_path = Path(repo_path)
        self._dependencies = dependencies
        self._extra_ignore_patterns = tuple(extra_ignore_patterns)
        self._entropy_cutoff = entropy_cutoff
        self._custom_patterns = tuple(custom_patterns)
        self._paths = (
            {path.replace("\\", "/") for path in paths} if paths is not None else None
        )

    def parse(self) -> RiskReport:
        markers: list[MarkerFinding] = []
        secrets: list[SecretFinding] = []
        for file_path in iter_text_files(
            self._repo_path,
            paths=self._paths,
            extra_ignore_patterns=self._extra_ignore_patterns,
        ):
            file_markers, file_secrets = scan_file_markers_and_secrets(
                file_path,
                self._repo_path,
                entropy_cutoff=self._entropy_cutoff,
                custom_patterns=self._custom_patterns,
            )
            markers.extend(file_markers)
            secrets.extend(file_secrets)

        return {
            "missing_tests": not has_test_directory(self._repo_path),
            "markers": markers,
            "secrets": secrets,
            "dependency_conflicts": check_dependency_conflicts(
                self._repo_path,
                self._dependencies,
                self._paths,
            ),
        }

    def _line_secret_confidence(
        self, line: str, relative_path: str
    ) -> Confidence | None:
        return line_secret_confidence(
            line,
            relative_path,
            entropy_cutoff=self._entropy_cutoff,
            custom_patterns=self._custom_patterns,
        )


__all__ = [
    "ENTROPY_THRESHOLD",
    "DependencyConflict",
    "MarkerFinding",
    "RiskReport",
    "RisksParser",
    "SecretFinding",
    "is_test_or_fixture_path",
    "line_secret_confidence",
]