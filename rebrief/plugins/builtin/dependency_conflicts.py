from __future__ import annotations

from rebrief.core.confidence import Confidence
from rebrief.plugins.base import BaseRiskDetector, RiskItem, ScanContext
from rebrief.plugins.builtin._helpers import check_dependency_conflicts


class DependencyConflictsDetector(BaseRiskDetector):
    name = "dependency-conflicts"
    description = "Detect duplicate package versions in dependency manifests"

    def scan(self, context: ScanContext) -> list[RiskItem]:
        path_set = set(context.paths) if context.paths is not None else None
        conflicts = check_dependency_conflicts(
            context.repo_path,
            list(context.stack["dependencies"]),
            path_set,
        )
        items: list[RiskItem] = []
        for conflict in conflicts:
            versions = ", ".join(conflict["versions"])
            items.append(
                {
                    "severity": "warning",
                    "message": (
                        f"Duplicate dependency `{conflict['package']}` "
                        f"with conflicting versions: {versions}."
                    ),
                    "confidence": Confidence.MEDIUM.value,
                }
            )
        return items
