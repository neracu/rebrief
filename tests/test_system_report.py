from pathlib import Path

from rebrief.core.reporter import ReportGenerator
from rebrief.core.system_report import (
    ScannedService,
    SystemReportGenerator,
    build_shared_dependencies,
    detect_infra_signals,
    format_architecture_line,
)
from rebrief.parsers.git_log import GitLogResult
from rebrief.parsers.manifests.versions import PackageSpec
from rebrief.parsers.risks import RiskReport
from rebrief.parsers.stack import StackResult


def _stack(
  frameworks: list[str] | None = None,
  packages: list[PackageSpec] | None = None,
) -> StackResult:
    return {
        "languages": ["JavaScript/TypeScript"],
        "manifests": ["package.json"],
        "frameworks": frameworks or [],
        "dependencies": [],
        "packages": packages or [],
        "is_empty": False,
        "manifest_warnings": [],
    }


def _git_log() -> GitLogResult:
    return {
        "commits": [],
        "top_modified_files": [{"file": "src/app.ts", "count": 5}],
        "status_message": None,
    }


def _risks() -> RiskReport:
    return {
        "missing_tests": False,
        "markers": [],
        "secrets": [],
        "dependency_conflicts": [],
    }


def _service(
    tmp_path: Path,
    name: str,
    *,
    frameworks: list[str] | None = None,
    packages: list[PackageSpec] | None = None,
) -> ScannedService:
    repo = tmp_path / name
    repo.mkdir()
    generator = ReportGenerator(
        str(repo),
        _stack(frameworks=frameworks, packages=packages),
        {},
        _git_log(),
        _risks(),
    )
    return ScannedService(name=name, source=str(repo), generator=generator)


def test_detect_infra_signals(tmp_path: Path) -> None:
    infra = tmp_path / "infra"
    infra.mkdir()
    (infra / "Dockerfile").write_text("FROM alpine\n", encoding="utf-8")
    (infra / "main.tf").write_text('resource "null_resource" "x" {}\n', encoding="utf-8")

    signals = detect_infra_signals(infra)
    assert "Docker" in signals
    assert "Terraform" in signals


def test_architecture_line_frontend_backend(tmp_path: Path) -> None:
    services = [
        _service(tmp_path, "frontend", frameworks=["Next.js", "React"]),
        _service(tmp_path, "backend", frameworks=["FastAPI"]),
    ]
    report = SystemReportGenerator(services)
    line = report.to_dict()["architecture_line"]
    assert "Frontend:" in line
    assert "Backend:" in line
    assert "Next.js" in line
    assert "FastAPI" in line


def test_shared_dependency_mismatch(tmp_path: Path) -> None:
    react_a: PackageSpec = {
        "name": "react",
        "version": "18.2.0",
        "ecosystem": "npm",
        "exact": True,
        "spec": "^18.2.0",
    }
    react_b: PackageSpec = {
        "name": "react",
        "version": "17.0.2",
        "ecosystem": "npm",
        "exact": True,
        "spec": "^17.0.2",
    }
    services = [
        _service(tmp_path, "web", packages=[react_a]),
        _service(tmp_path, "admin", packages=[react_b]),
    ]
    shared = build_shared_dependencies(services)
    assert len(shared) == 1
    assert shared[0]["kind"] == "mismatch"
    assert shared[0]["package"] == "react"


def test_unified_risks_prefixed(tmp_path: Path) -> None:
    risks: RiskReport = {
        "missing_tests": True,
        "markers": [],
        "secrets": [],
        "dependency_conflicts": [],
    }
    repo = tmp_path / "api"
    repo.mkdir()
    generator = ReportGenerator(
        str(repo),
        _stack(frameworks=["FastAPI"]),
        {},
        _git_log(),
        risks,
    )
    services = [ScannedService(name="api", source=str(repo), generator=generator)]
    report = SystemReportGenerator(services)
    warnings = report.to_dict()["risk_map"]["warning"]
    assert any(item["message"].startswith("[api]") for item in warnings)


def test_generate_markdown_sections(tmp_path: Path) -> None:
    services = [
        _service(tmp_path, "frontend", frameworks=["React"]),
        _service(tmp_path, "backend", frameworks=["FastAPI"]),
    ]
    markdown = SystemReportGenerator(services).generate()
    assert "# REBRIEF SYSTEM REPORT" in markdown
    assert "## 2. System Architecture Summary" in markdown
    assert "## 3. Cross-Repo Hotspot Matrix" in markdown
    assert "## 5. Shared Dependency Graph" in markdown
    assert "## Service: frontend" in markdown
    assert "## Service: backend" in markdown


def test_generate_json_payload(tmp_path: Path) -> None:
    services = [_service(tmp_path, "frontend", frameworks=["React"])]
    payload = SystemReportGenerator(services).to_dict()
    assert payload["kind"] == "system"
    assert payload["summary"]["services_count"] == 1
    assert len(payload["services"]) == 1
