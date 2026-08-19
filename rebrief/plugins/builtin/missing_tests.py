from __future__ import annotations

from rebrief.core.confidence import Confidence
from rebrief.plugins.base import BaseRiskDetector, RiskItem, ScanContext
from rebrief.plugins.builtin._helpers import has_test_directory


class MissingTestsDetector(BaseRiskDetector):
    name = "missing-tests"
    description = "Check for a tests directory at the repository root"

    def scan(self, context: ScanContext) -> list[RiskItem]:
        if has_test_directory(context.repo_path):
            return []
        return [
            {
                "severity": "warning",
                "message": (
                    "Missing tests directory (`tests/`, `test/`, or `__tests__/`)."
                ),
                "confidence": Confidence.HIGH.value,
            }
        ]
