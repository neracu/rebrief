from __future__ import annotations

from rebrief.plugins.builtin.dependency_conflicts import DependencyConflictsDetector
from rebrief.plugins.builtin.markers import MarkersDetector
from rebrief.plugins.builtin.missing_tests import MissingTestsDetector
from rebrief.plugins.builtin.secrets import SecretsDetector
from rebrief.plugins.base import BaseRiskDetector

BUILTIN_PLUGINS: tuple[type[BaseRiskDetector], ...] = (
    SecretsDetector,
    MarkersDetector,
    MissingTestsDetector,
    DependencyConflictsDetector,
)

__all__ = [
    "BUILTIN_PLUGINS",
    "DependencyConflictsDetector",
    "MarkersDetector",
    "MissingTestsDetector",
    "SecretsDetector",
]
