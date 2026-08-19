from pathlib import Path
import json
from xml.etree import ElementTree as ET

from rebrief import __version__
from rebrief.core.confidence import Confidence
from rebrief.core.reporter import ReportGenerator
from rebrief.parsers.git_log import POINT_ZERO_MESSAGE, GitLogResult
from rebrief.parsers.risks import RiskReport
from rebrief.parsers.rules import RuleFileEntry
from rebrief.parsers.stack import StackResult


def make_report_data() -> tuple[
    StackResult,
    dict[str, RuleFileEntry],
    GitLogResult,
    RiskReport,
]:
    stack: StackResult = {
        "languages": ["Python"],
        "manifests": ["pyproject.toml"],
        "frameworks": ["Django"],
        "dependencies": ["click>=8.1", "django==4.2"],
        "is_empty": False,
        "manifest_warnings": [],
    }
    rules: dict[str, RuleFileEntry] = {
        ".cursorrules": {"content": "# Rules", "lines_count": 12},
        "CLAUDE.md": {"content": "# Claude", "lines_count": 5},
    }
    git_log: GitLogResult = {
        "commits": [
            {
                "hash": "a1b2c3d",
                "author": "Alice",
                "date": "2026-01-15",
                "subject": "Add authentication module",
            }
        ],
        "top_modified_files": [
            {"file": "src/app.py", "count": 8},
        ],
        "status_message": None,
    }
    risks: RiskReport = {
        "missing_tests": True,
        "markers": [
            {"file": "app.py", "line": 10, "marker": "TODO", "confidence": "LOW"}
        ],
        "secrets": [{"file": "config.py", "line": 3, "confidence": "MEDIUM"}],
        "dependency_conflicts": [
            {"package": "django", "versions": ["==3.2", "==4.2"]},
        ],
    }
    return stack, rules, git_log, risks


def _make_generator(tmp_path: Path) -> ReportGenerator:
    stack, rules, git_log, risks = make_report_data()
    return ReportGenerator(str(tmp_path / "demo-repo"), stack, rules, git_log, risks)


def test_generate_includes_all_sections(tmp_path: Path) -> None:
    report = _make_generator(tmp_path).generate()

    assert "# REBRIEF REPORT: demo-repo" in report
    assert "## 1. Project Overview (Executive Summary)" in report
    assert "## 2. Technology Stack and Dependencies" in report
    assert "## 3. Solution Timeline (Git History)" in report
    assert "## 4. Risk Map (AI Debt & Security)" in report
    assert '## 5. Developer Checklist ("Where to Start")' in report


def test_generate_critical_warning_info(tmp_path: Path) -> None:
    stack, rules, git_log, risks = make_report_data()
    generator = ReportGenerator(
        str(tmp_path / "demo-repo"),
        stack,
        rules,
        git_log,
        risks,
        min_confidence=Confidence.LOW,
    )
    report = generator.generate()

    assert "### [CRITICAL]" in report
    assert "[Confidence: MEDIUM] Hard-coded secret in config.py:3" in report
    assert "### [WARNING]" in report
    assert "[Confidence: HIGH] Missing tests directory" in report
    assert "[Confidence: MEDIUM] Duplicate dependency `django`" in report
    assert "### [INFO]" in report
    assert "[Confidence: LOW] TODO in app.py:10 (Requires Verification)" in report


def test_generate_stack_section(tmp_path: Path) -> None:
    report = _make_generator(tmp_path).generate()

    assert "**Languages:** Python" in report
    assert "**Frameworks:** Django" in report
    assert "**Manifests:** pyproject.toml" in report
    assert "`click>=8.1`" in report
    assert "`django==4.2`" in report


def test_generate_timeline_and_hotspots(tmp_path: Path) -> None:
    report = _make_generator(tmp_path).generate()

    assert "`a1b2c3d` (2026-01-15) Add authentication module — Alice" in report
    assert "### Hotspots (Change Density)" in report
    assert "src/app.py: 8 changes" in report


def test_generate_checklist_from_risks(tmp_path: Path) -> None:
    report = _make_generator(tmp_path).generate()

    assert "1. Review and rotate hard-coded credentials in config.py (line 3)." in report
    assert "2. Add a `tests/` directory and cover critical paths." in report
    assert "Resolve version conflict for `django`" in report
    assert "Set up the development environment for Django." in report
    assert "Review frequently changed file: src/app.py (8 edits in 30 days)." in report


def test_write_report_creates_file(tmp_path: Path) -> None:
    output_path = tmp_path / "REBRIEF.md"
    generator = _make_generator(tmp_path)

    generator.write_report(output_path)

    content = output_path.read_text(encoding="utf-8")
    assert "# REBRIEF REPORT: demo-repo" in content
    assert "## 4. Risk Map (AI Debt & Security)" in content


def test_write_report_default_filename(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    generator = _make_generator(tmp_path)

    generator.write_report()

    output_path = tmp_path / "REBRIEF.md"
    assert output_path.is_file()
    assert "# REBRIEF REPORT: demo-repo" in output_path.read_text(encoding="utf-8")


def test_generate_empty_repo_overview(tmp_path: Path) -> None:
    stack: StackResult = {
        "languages": [],
        "manifests": [],
        "frameworks": [],
        "dependencies": [],
        "is_empty": True,
        "manifest_warnings": [],
    }
    git_log: GitLogResult = {
        "commits": [],
        "top_modified_files": [],
        "status_message": POINT_ZERO_MESSAGE,
    }
    risks: RiskReport = {
        "missing_tests": True,
        "markers": [],
        "secrets": [],
        "dependency_conflicts": [],
    }
    generator = ReportGenerator(str(tmp_path / "empty-repo"), stack, {}, git_log, risks)

    report = generator.generate()

    assert "Empty repository detected." in report


def test_generate_point_zero_git_timeline(tmp_path: Path) -> None:
    stack, rules, _, risks = make_report_data()
    git_log: GitLogResult = {
        "commits": [],
        "top_modified_files": [],
        "status_message": POINT_ZERO_MESSAGE,
    }
    generator = ReportGenerator(str(tmp_path / "demo-repo"), stack, rules, git_log, risks)

    report = generator.generate()

    assert POINT_ZERO_MESSAGE in report


def test_generate_monorepo_manifests(tmp_path: Path) -> None:
    stack: StackResult = {
        "languages": ["Go", "JavaScript/TypeScript", "Python", "Rust"],
        "manifests": [
            "Cargo.toml",
            "backend/requirements.txt",
            "frontend/package.json",
            "go.mod",
        ],
        "frameworks": ["Django"],
        "dependencies": ["django==4.2"],
        "is_empty": False,
        "manifest_warnings": [],
    }
    git_log: GitLogResult = {
        "commits": [],
        "top_modified_files": [],
        "status_message": None,
    }
    risks: RiskReport = {
        "missing_tests": False,
        "markers": [],
        "secrets": [],
        "dependency_conflicts": [],
    }
    generator = ReportGenerator(str(tmp_path / "monorepo"), stack, {}, git_log, risks)

    report = generator.generate()

    assert (
        "**Manifests:** Cargo.toml, backend/requirements.txt, frontend/package.json, go.mod"
        in report
    )


def test_to_dict_structure(tmp_path: Path) -> None:
    payload = _make_generator(tmp_path).to_dict()

    assert payload["version"] == __version__
    assert set(payload.keys()) == {
        "version",
        "mode",
        "diff_ref",
        "summary",
        "tech_stack",
        "timeline",
        "risk_map",
        "checklist",
    }
    assert payload["mode"] == "full"
    assert payload["diff_ref"] is None
    assert set(payload["summary"].keys()) == {
        "languages_count",
        "risks_count",
        "ai_instruction_files",
        "badge_url",
        "badge_markdown",
        "files_scanned",
        "files_total",
        "token_stats",
    }
    assert set(payload["tech_stack"].keys()) == {
        "languages",
        "frameworks",
        "manifests",
        "dependencies",
    }
    assert set(payload["timeline"].keys()) == {"recent_commits", "hotspots"}
    assert set(payload["risk_map"].keys()) == {
        "critical",
        "warning",
        "info",
        "vulnerabilities",
    }


def test_incremental_report_metadata(tmp_path: Path) -> None:
    from rebrief.core.diff import DiffScope

    stack, rules, git_log, risks = make_report_data()
    scope: DiffScope = {
        "ref": "origin/main",
        "files": ["a.py", "b.py", "c.py", "d.py"],
        "files_scanned": 4,
        "files_total": 128,
    }
    generator = ReportGenerator(
        str(tmp_path / "demo-repo"),
        stack,
        rules,
        git_log,
        risks,
        diff_scope=scope,
    )

    report = generator.generate()
    payload = generator.to_dict()

    assert "# REBRIEF INCREMENTAL REPORT (Diff against origin/main)" in report
    assert "Files scanned in diff: 4 / Total files: 128." in report
    assert payload["mode"] == "incremental"
    assert payload["diff_ref"] == "origin/main"
    assert payload["summary"]["files_scanned"] == 4
    assert payload["summary"]["files_total"] == 128


def test_to_dict_field_mapping(tmp_path: Path) -> None:
    payload = _make_generator(tmp_path).to_dict()

    assert payload["summary"]["languages_count"] == 1
    assert payload["summary"]["risks_count"] == 3
    assert payload["summary"]["ai_instruction_files"] == [".cursorrules", "CLAUDE.md"]
    assert (
        payload["summary"]["badge_url"]
        == "https://img.shields.io/badge/rebrief-1%20critical-red"
    )
    assert payload["summary"]["badge_markdown"] == (
        "[![Rebrief](https://img.shields.io/badge/rebrief-1%20critical-red)]"
        "(https://github.com/neracu/rebrief)"
    )
    assert payload["timeline"]["recent_commits"] == [
        {
            "hash": "a1b2c3d",
            "date": "2026-01-15",
            "message": "Add authentication module",
            "author": "Alice",
        }
    ]
    assert payload["timeline"]["hotspots"] == [{"file": "src/app.py", "changes": 8}]
    assert payload["risk_map"]["critical"] == [
        {
            "message": "Hard-coded secret in config.py:3",
            "confidence": "MEDIUM",
        }
    ]
    assert payload["risk_map"]["warning"][0]["message"].startswith("Missing tests directory")
    assert payload["risk_map"]["warning"][0]["confidence"] == "HIGH"
    assert payload["risk_map"]["info"] == []
    assert "Review and rotate hard-coded credentials in config.py (line 3)." in payload["checklist"]


def test_to_dict_empty_risks(tmp_path: Path) -> None:
    stack: StackResult = {
        "languages": ["Python"],
        "manifests": ["pyproject.toml"],
        "frameworks": [],
        "dependencies": [],
        "is_empty": False,
        "manifest_warnings": [],
    }
    git_log: GitLogResult = {
        "commits": [],
        "top_modified_files": [],
        "status_message": None,
    }
    risks: RiskReport = {
        "missing_tests": False,
        "markers": [],
        "secrets": [],
        "dependency_conflicts": [],
    }
    generator = ReportGenerator(str(tmp_path / "clean-repo"), stack, {}, git_log, risks)
    payload = generator.to_dict()

    assert payload["risk_map"] == {
        "critical": [],
        "warning": [],
        "info": [],
        "vulnerabilities": [],
    }
    assert payload["summary"]["risks_count"] == 0


def test_manifest_warning_in_risk_map(tmp_path: Path) -> None:
    stack: StackResult = {
        "languages": ["PHP"],
        "manifests": ["composer.json"],
        "frameworks": [],
        "dependencies": [],
        "is_empty": False,
        "manifest_warnings": [
            "Malformed manifest: composer.json (Could not parse composer.json: ...)"
        ],
    }
    git_log: GitLogResult = {
        "commits": [],
        "top_modified_files": [],
        "status_message": None,
    }
    risks: RiskReport = {
        "missing_tests": False,
        "markers": [],
        "secrets": [],
        "dependency_conflicts": [],
    }
    generator = ReportGenerator(str(tmp_path / "warn-repo"), stack, {}, git_log, risks)
    payload = generator.to_dict()

    assert payload["summary"]["risks_count"] == 1
    assert payload["risk_map"]["warning"][0]["message"].startswith("Malformed manifest: composer.json")
    assert payload["risk_map"]["warning"][0]["confidence"] == "HIGH"


def test_generate_json_valid(tmp_path: Path) -> None:
    payload = json.loads(_make_generator(tmp_path).generate_json())

    assert payload["version"] == __version__
    assert payload["tech_stack"]["languages"] == ["Python"]


def test_tech_stack_frameworks_in_json_output(tmp_path: Path) -> None:
    frameworks = ["Axum", "Echo", "Express", "Flask", "React", "Sinatra", "Slim", "Vite"]
    stack: StackResult = {
        "languages": ["Go", "JavaScript/TypeScript", "PHP", "Python", "Ruby", "Rust"],
        "manifests": [
            "Cargo.toml",
            "composer.json",
            "Gemfile",
            "go.mod",
            "package.json",
            "requirements.txt",
        ],
        "frameworks": frameworks,
        "dependencies": [],
        "is_empty": False,
        "manifest_warnings": [],
    }
    git_log: GitLogResult = {
        "commits": [],
        "top_modified_files": [],
        "status_message": None,
    }
    risks: RiskReport = {
        "missing_tests": False,
        "markers": [],
        "secrets": [],
        "dependency_conflicts": [],
    }
    generator = ReportGenerator(str(tmp_path / "multi-stack"), stack, {}, git_log, risks)
    payload = generator.to_dict()

    assert payload["tech_stack"]["frameworks"] == frameworks


def test_write_json_report_creates_file(tmp_path: Path) -> None:
    output_path = tmp_path / "REBRIEF.json"
    generator = _make_generator(tmp_path)

    generator.write_json_report(output_path)

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["version"] == __version__
    assert payload["tech_stack"]["frameworks"] == ["Django"]


def test_generate_xml_structure(tmp_path: Path) -> None:
    xml_text = _make_generator(tmp_path).generate_xml()

    assert xml_text.startswith('<?xml version="1.0" encoding="UTF-8"?>\n')
    assert xml_text.endswith("\n")
    root = ET.fromstring(xml_text)
    assert root.tag == "rebrief"
    assert root.attrib["version"] == __version__
    assert [child.tag for child in root] == [
        "summary",
        "tech_stack",
        "hotspots",
        "risk_map",
        "checklist",
    ]

    summary = {child.tag: child.text for child in root.find("summary")}
    assert summary["languages_count"] == "1"
    assert summary["risks_count"] == "3"
    assert summary["raw_tokens"] is not None
    assert int(summary["brief_tokens"]) > 0
    assert "." in summary["savings_percentage"]

    languages = [el.text for el in root.find("tech_stack/languages")]
    frameworks = [el.text for el in root.find("tech_stack/frameworks")]
    manifests = [el.text for el in root.find("tech_stack/manifests")]
    assert languages == ["Python"]
    assert frameworks == ["Django"]
    assert manifests == ["pyproject.toml"]
    assert root.find("tech_stack/dependencies") is None

    hotspot = root.find("hotspots/hotspot")
    assert hotspot is not None
    assert hotspot.attrib == {"file": "src/app.py", "changes": "8"}

    risks = list(root.find("risk_map"))
    assert [risk.attrib["severity"] for risk in risks] == ["CRITICAL", "WARNING", "WARNING"]
    assert risks[0].attrib["confidence"] == "MEDIUM"
    assert risks[0].text == "Hard-coded secret in config.py:3"
    assert risks[1].text.startswith("Missing tests directory")

    items = [el.text for el in root.find("checklist")]
    assert "Review and rotate hard-coded credentials in config.py (line 3)." in items


def test_generate_xml_empty_containers(tmp_path: Path) -> None:
    stack: StackResult = {
        "languages": ["Python"],
        "manifests": ["pyproject.toml"],
        "frameworks": [],
        "dependencies": [],
        "is_empty": False,
        "manifest_warnings": [],
    }
    git_log: GitLogResult = {
        "commits": [],
        "top_modified_files": [],
        "status_message": None,
    }
    risks: RiskReport = {
        "missing_tests": False,
        "markers": [],
        "secrets": [],
        "dependency_conflicts": [],
    }
    generator = ReportGenerator(str(tmp_path / "empty-xml"), stack, {}, git_log, risks)
    root = ET.fromstring(generator.generate_xml())

    assert root.find("tech_stack/frameworks") is not None
    assert list(root.find("tech_stack/frameworks")) == []
    assert root.find("hotspots") is not None
    assert list(root.find("hotspots")) == []
    assert root.find("risk_map") is not None
    assert list(root.find("risk_map")) == []


def test_generate_xml_escapes_special_characters(tmp_path: Path) -> None:
    stack: StackResult = {
        "languages": ["C++"],
        "manifests": ["a&b.xml"],
        "frameworks": ["Foo<Bar>"],
        "dependencies": [],
        "is_empty": False,
        "manifest_warnings": [],
    }
    git_log: GitLogResult = {
        "commits": [],
        "top_modified_files": [{"file": "src/a&b.ts", "count": 2}],
        "status_message": None,
    }
    risks: RiskReport = {
        "missing_tests": False,
        "markers": [],
        "secrets": [{"file": "cfg<x>.py", "line": 1, "confidence": "HIGH"}],
        "dependency_conflicts": [],
    }
    xml_text = ReportGenerator(
        str(tmp_path / "escape-repo"), stack, {}, git_log, risks
    ).generate_xml()

    assert "&amp;" in xml_text
    assert "&lt;" in xml_text
    root = ET.fromstring(xml_text)
    assert root.find("tech_stack/languages/language").text == "C++"
    assert root.find("tech_stack/manifests/manifest").text == "a&b.xml"
    assert root.find("tech_stack/frameworks/framework").text == "Foo<Bar>"
    assert root.find("hotspots/hotspot").attrib["file"] == "src/a&b.ts"
    assert "cfg<x>.py" in root.find("risk_map/risk").text


def test_write_xml_report_creates_file(tmp_path: Path) -> None:
    output_path = tmp_path / "REBRIEF.xml"
    generator = _make_generator(tmp_path)

    generator.write_xml_report(output_path)

    xml_text = output_path.read_text(encoding="utf-8")
    root = ET.fromstring(xml_text)
    assert root.attrib["version"] == __version__
    assert root.find("tech_stack/frameworks/framework").text == "Django"


def test_min_confidence_filters_low_info_items(tmp_path: Path) -> None:
    stack, rules, git_log, risks = make_report_data()
    generator = ReportGenerator(
        str(tmp_path / "demo-repo"),
        stack,
        rules,
        git_log,
        risks,
        min_confidence=Confidence.MEDIUM,
    )

    report = generator.generate()

    assert "Missing tests directory" in report
    assert "TODO in app.py:10" not in report
    assert generator.filtered_risk_count() == 3


def test_min_confidence_high_excludes_medium_items(tmp_path: Path) -> None:
    stack, rules, git_log, risks = make_report_data()
    generator = ReportGenerator(
        str(tmp_path / "demo-repo"),
        stack,
        rules,
        git_log,
        risks,
        min_confidence=Confidence.HIGH,
    )
    payload = generator.to_dict()

    assert payload["risk_map"]["critical"] == []
    assert len(payload["risk_map"]["warning"]) == 1
    assert payload["risk_map"]["warning"][0]["confidence"] == "HIGH"
    assert payload["risk_map"]["info"] == []
    assert generator.filtered_risk_count() == 1
