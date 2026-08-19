from __future__ import annotations

from rebrief.plugins.base import BaseRiskDetector, RiskItem, ScanContext
from rebrief.plugins.builtin._helpers import scan_file_markers_and_secrets


class MarkersDetector(BaseRiskDetector):
    name = "markers"
    description = "Flag TODO, FIXME, HACK, and BUG markers in source files"

    def scan(self, context: ScanContext) -> list[RiskItem]:
        items: list[RiskItem] = []
        custom_patterns = context.settings.custom_secret_patterns
        for file_path in context.iter_text_files():
            markers, _ = scan_file_markers_and_secrets(
                file_path,
                context.repo_path,
                entropy_cutoff=context.settings.entropy_cutoff,
                custom_patterns=custom_patterns,
            )
            for entry in markers:
                items.append(
                    {
                        "severity": "info",
                        "message": (
                            f"{entry['marker']} in {entry['file']}:{entry['line']}"
                        ),
                        "confidence": entry["confidence"],
                    }
                )
        return items
