from __future__ import annotations

from rebrief.plugins.base import BaseRiskDetector, RiskItem, ScanContext
from rebrief.plugins.builtin._helpers import (
    scan_file_markers_and_secrets,
    secret_finding_to_risk_item,
)


class SecretsDetector(BaseRiskDetector):
    name = "secrets"
    description = "Detect hard-coded credentials in source files"

    def scan(self, context: ScanContext) -> list[RiskItem]:
        items: list[RiskItem] = []
        custom_patterns = context.settings.custom_secret_patterns
        for file_path in context.iter_text_files():
            _, secrets = scan_file_markers_and_secrets(
                file_path,
                context.repo_path,
                entropy_cutoff=context.settings.entropy_cutoff,
                custom_patterns=custom_patterns,
            )
            for entry in secrets:
                items.append(secret_finding_to_risk_item(entry))
        return items
