from pathlib import Path

from rebrief.core.reporter import ReportGenerator
from rebrief.parsers.git_log import GitLogResult
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
    }
    risks: RiskReport = {
        "missing_tests": True,
        "markers": [{"file": "app.py", "line": 10, "marker": "TODO"}],
        "secrets": [{"file": "config.py", "line": 3}],
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
    report = _make_generator(tmp_path).generate()

    assert "### [CRITICAL]" in report
    assert "Hard-coded secret in config.py:3" in report
    assert "### [WARNING]" in report
    assert "Missing tests directory" in report
    assert "Duplicate dependency `django`" in report
    assert "### [INFO]" in report
    assert "TODO in app.py:10" in report


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
