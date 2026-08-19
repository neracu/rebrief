from rebrief.plugins.base import BaseRiskDetector, RiskItem, ScanContext


class FailingDetector(BaseRiskDetector):
    name = "failing-detector"
    description = "Test plugin that always raises during scan"

    def scan(self, context: ScanContext) -> list[RiskItem]:
        raise RuntimeError("plugin boom")
