from __future__ import annotations

import pytest

from rebrief.core.vulnerabilities import VulnerabilityReport, check_vulnerabilities


@pytest.fixture(autouse=True)
def _disable_live_osv_checks(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    if request.node.get_closest_marker("osv_network"):
        return

    def _noop(
        packages: list[object],
        *,
        skip: bool = False,
        timeout: float = 3.0,
        transport: object | None = None,
    ) -> VulnerabilityReport:
        return {
            "findings": [],
            "skipped": False,
            "skip_message": None,
        }

    monkeypatch.setattr("rebrief.core.scan.check_vulnerabilities", _noop)
