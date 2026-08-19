from __future__ import annotations

import json
from typing import Any

import pytest
from click.testing import CliRunner

from rebrief.cli import main
from rebrief.core.reporter import ReportGenerator
from rebrief.core.vulnerabilities import (
    SKIP_MESSAGE,
    VulnerabilityReport,
    check_vulnerabilities,
)
from rebrief.parsers.manifests.versions import PackageSpec
from tests.test_reporter import make_report_data


class FakeTransport:
    def __init__(self, responses: dict[tuple[str, str], tuple[int, bytes]]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, str, bytes | None]] = []

    def __call__(
        self,
        method: str,
        url: str,
        body: bytes | None,
        timeout: float,
    ) -> tuple[int, bytes]:
        self.calls.append((method, url, body))
        key = (method, url)
        if key in self.responses:
            return self.responses[key]
        if method == "GET" and "/v1/vulns/" in url:
            vuln_id = url.rsplit("/", 1)[-1]
            for (call_method, call_url), response in self.responses.items():
                if call_method == "GET" and vuln_id in call_url:
                    return response
        raise AssertionError(f"Unexpected transport call: {method} {url}")


def _critical_vuln() -> dict[str, Any]:
    return {
        "id": "GHSA-xxxx-yyyy-zzzz",
        "summary": "Critical remote code execution",
        "severity": [{"type": "CVSS_V3", "score": "9.8"}],
        "affected": [
            {
                "package": {"name": "lodash", "ecosystem": "npm"},
                "ranges": [
                    {
                        "events": [
                            {"introduced": "0"},
                            {"fixed": "4.17.21"},
                        ]
                    }
                ],
            }
        ],
    }


def _warning_vuln() -> dict[str, Any]:
    return {
        "id": "CVE-2024-12345",
        "summary": "Moderate information disclosure",
        "database_specific": {"severity": "MODERATE"},
        "affected": [
            {
                "package": {"name": "django", "ecosystem": "PyPI"},
                "ranges": [
                    {
                        "events": [
                            {"introduced": "0"},
                            {"fixed": "4.2.11"},
                        ]
                    }
                ],
            }
        ],
    }


@pytest.mark.osv_network
def test_check_vulnerabilities_maps_severity_and_fixed_versions() -> None:
    batch_response = {
        "results": [
            {"vulns": [{"id": "GHSA-xxxx-yyyy-zzzz", "modified": "2024-01-01T00:00:00Z"}]},
            {"vulns": [{"id": "CVE-2024-12345", "modified": "2024-01-02T00:00:00Z"}]},
        ]
    }
    transport = FakeTransport(
        {
            ("POST", "https://api.osv.dev/v1/querybatch"): (
                200,
                json.dumps(batch_response).encode("utf-8"),
            ),
            (
                "GET",
                "https://api.osv.dev/v1/vulns/GHSA-xxxx-yyyy-zzzz",
            ): (200, json.dumps(_critical_vuln()).encode("utf-8")),
            (
                "GET",
                "https://api.osv.dev/v1/vulns/CVE-2024-12345",
            ): (200, json.dumps(_warning_vuln()).encode("utf-8")),
        }
    )
    packages: list[PackageSpec] = [
        {
            "name": "lodash",
            "version": "4.17.20",
            "ecosystem": "npm",
            "exact": True,
            "spec": "4.17.20",
        },
        {
            "name": "django",
            "version": "4.2.0",
            "ecosystem": "PyPI",
            "exact": False,
            "spec": "django>=4.2.0",
        },
    ]

    report = check_vulnerabilities(packages, transport=transport)

    assert report["skipped"] is False
    assert len(report["findings"]) == 2
    critical = next(item for item in report["findings"] if item["id"] == "GHSA-xxxx-yyyy-zzzz")
    warning = next(item for item in report["findings"] if item["id"] == "CVE-2024-12345")
    assert critical["severity"] == "critical"
    assert critical["fixed_in"] == "4.17.21"
    assert critical["confidence"] == "HIGH"
    assert warning["severity"] == "warning"
    assert warning["fixed_in"] == "4.2.11"
    assert warning["confidence"] == "MEDIUM"


@pytest.mark.osv_network
def test_check_vulnerabilities_offline_fallback() -> None:
    def failing_transport(
        method: str,
        url: str,
        body: bytes | None,
        timeout: float,
    ) -> tuple[int, bytes]:
        raise OSError("network down")

    packages: list[PackageSpec] = [
        {
            "name": "django",
            "version": "4.2.0",
            "ecosystem": "PyPI",
            "exact": True,
            "spec": "django==4.2.0",
        }
    ]

    report = check_vulnerabilities(packages, transport=failing_transport)

    assert report == {
        "findings": [],
        "skipped": True,
        "skip_message": SKIP_MESSAGE,
    }


@pytest.mark.osv_network
def test_check_vulnerabilities_skip_flag() -> None:
    def boom_transport(
        method: str,
        url: str,
        body: bytes | None,
        timeout: float,
    ) -> tuple[int, bytes]:
        raise AssertionError("transport should not be called when skip=True")

    report = check_vulnerabilities(
        [
            {
                "name": "django",
                "version": "4.2.0",
                "ecosystem": "PyPI",
                "exact": True,
                "spec": "django==4.2.0",
            }
        ],
        skip=True,
        transport=boom_transport,
    )

    assert report["findings"] == []
    assert report["skipped"] is False


@pytest.mark.osv_network
def test_report_generator_includes_vulnerability_section() -> None:
    stack, rules, git_log, risks = make_report_data()
    vulnerabilities: VulnerabilityReport = {
        "findings": [
            {
                "id": "GHSA-xxxx-yyyy-zzzz",
                "package": "lodash",
                "severity": "critical",
                "fixed_in": "4.17.21",
                "summary": "Critical remote code execution",
                "confidence": "HIGH",
            }
        ],
        "skipped": False,
        "skip_message": None,
    }
    generator = ReportGenerator(
        "repo",
        stack,
        rules,
        git_log,
        risks,
        vulnerabilities=vulnerabilities,
    )

    markdown = generator.generate()
    payload = generator.to_dict()

    assert "### 🛡️ Vulnerability Report" in markdown
    assert "GHSA-xxxx-yyyy-zzzz" in markdown
    assert "upgrade to `4.17.21`" in markdown
    assert payload["risk_map"]["vulnerabilities"][0]["id"] == "GHSA-xxxx-yyyy-zzzz"
    assert any("GHSA-xxxx-yyyy-zzzz" in item["message"] for item in payload["risk_map"]["critical"])


@pytest.mark.osv_network
def test_report_generator_offline_notice_in_info_tier() -> None:
    stack, rules, git_log, risks = make_report_data()
    vulnerabilities: VulnerabilityReport = {
        "findings": [],
        "skipped": True,
        "skip_message": SKIP_MESSAGE,
    }
    generator = ReportGenerator(
        "repo",
        stack,
        rules,
        git_log,
        risks,
        vulnerabilities=vulnerabilities,
    )
    payload = generator.to_dict()

    assert any(SKIP_MESSAGE in item["message"] for item in payload["risk_map"]["info"])


def test_scan_skip_vulnerability_check_flag(tmp_path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_app.py").write_text("def test_ok() -> None:\n    pass\n", encoding="utf-8")
    (tmp_path / "requirements.txt").write_text("django==4.2\n", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["scan", str(tmp_path), "--skip-vulnerability-check", "-y"],
    )

    assert result.exit_code == 0
    report = (tmp_path / "REBRIEF.md").read_text(encoding="utf-8")
    assert "### 🛡️ Vulnerability Report" not in report
