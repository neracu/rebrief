from __future__ import annotations

import re
from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal, TypedDict

from rebrief.core.confidence import Confidence

if TYPE_CHECKING:
    from rebrief.parsers.git_log import GitLogResult
    from rebrief.parsers.ownership import OwnershipResult
    from rebrief.parsers.stack import StackResult


class RiskItem(TypedDict):
    severity: Literal["critical", "warning", "info"]
    message: str
    confidence: str


@dataclass(frozen=True)
class PluginScanSettings:
    entropy_cutoff: float
    extra_ignore_patterns: tuple[str, ...]
    custom_secret_patterns: tuple[tuple[re.Pattern[str], Confidence], ...]
    min_confidence: str


@dataclass(frozen=True)
class ScanContext:
    repo_path: Path
    stack: StackResult
    git_log: GitLogResult
    ownership: OwnershipResult
    paths: tuple[str, ...] | None
    settings: PluginScanSettings

    def iter_text_files(self) -> Iterator[Path]:
        from rebrief.plugins.context import iter_text_files

        return iter_text_files(
            self.repo_path,
            paths=self.paths,
            extra_ignore_patterns=self.settings.extra_ignore_patterns,
        )

    def repo_root_files(self) -> list[str]:
        try:
            return sorted(entry.name for entry in self.repo_path.iterdir())
        except OSError:
            return []


class BaseRiskDetector(ABC):
    name: str
    description: str

    @abstractmethod
    def scan(self, context: ScanContext) -> list[RiskItem]:
        """Analyze parsed codebase context and return detected risks."""
