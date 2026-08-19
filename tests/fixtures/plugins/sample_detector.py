from rebrief.plugins.base import BaseRiskDetector, RiskItem, ScanContext


class SampleDetector(BaseRiskDetector):
    name = "sample-detector"
    description = "Test plugin that reports a fixed warning"

    def scan(self, context: ScanContext) -> list[RiskItem]:
        return [
            {
                "severity": "warning",
                "message": "Sample plugin detected a custom risk.",
                "confidence": "HIGH",
            }
        ]
