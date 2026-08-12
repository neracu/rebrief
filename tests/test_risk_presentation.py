from pathlib import Path

import pytest

from rebrief.core.confidence import Confidence
from rebrief.core.reporter import ReportGenerator
from rebrief.parsers.git_log import GitLogResult
from rebrief.parsers.risks import RisksParser, is_test_or_fixture_path
from rebrief.parsers.stack import StackResult
from tests.test_reporter import make_report_data

REPO_ROOT = Path(__file__).resolve().parents[1]
SECRET_LINE = 'api_key = "aB3xQ9mK7pL2wZ8vN4tR"\n'
TODO_LINE = "# TODO review later\n"


def _empty_stack() -> StackResult:
    return {
        "languages": ["Python"],
        "manifests": [],
        "frameworks": [],
        "dependencies": [],
        "is_empty": False,
        "manifest_warnings": [],
    }


def _empty_git() -> GitLogResult:
    return {"commits": [], "top_modified_files": [], "status_message": None}


def _report_for(
    repo: Path, min_confidence: Confidence = Confidence.MEDIUM
) -> tuple[str, dict]:
    risks = RisksParser(str(repo)).parse()
    generator = ReportGenerator(
        str(repo),
        _empty_stack(),
        {},
        _empty_git(),
        risks,
        min_confidence=min_confidence,
    )
    return generator.generate(), generator.to_dict()


@pytest.mark.parametrize(
    ("relative", "expected"),
    [
        ("tests/test_app.py", True),
        ("test/app.py", True),
        ("__tests__/app.js", True),
        ("spec/models_spec.rb", True),
        ("fixtures/secrets/aws_config.py", True),
        ("tests/fixtures/secrets/aws_config.py", True),
        ("src/config.py", False),
        ("contest/app.py", False),
        ("src/test_utils.py", False),
        ("latest/config.py", False),
        ("packages/my-test/config.py", False),
    ],
)
def test_is_test_or_fixture_path(relative: str, expected: bool) -> None:
    assert is_test_or_fixture_path(relative) is expected


def test_production_secret_is_critical_and_asks_to_rotate(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "config.py").write_text(SECRET_LINE, encoding="utf-8")

    report, payload = _report_for(tmp_path)

    assert payload["risk_map"]["critical"] == [
        {"message": "Hard-coded secret in config.py:1", "confidence": "MEDIUM"}
    ]
    assert all(
        "secret-like value" not in item["message"]
        for item in payload["risk_map"]["warning"]
    )
    assert "Review and rotate hard-coded credentials in config.py (line 1)." in report
    assert "test/example file" not in report


@pytest.mark.parametrize(
    "relative",
    [
        "tests/config.py",
        "test/config.py",
        "__tests__/config.py",
        "spec/config.py",
        "fixtures/config.py",
    ],
)
def test_test_or_fixture_secret_is_warning_not_rotate(
    tmp_path: Path, relative: str
) -> None:
    (tmp_path / "tests").mkdir(exist_ok=True)
    path = tmp_path / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(SECRET_LINE, encoding="utf-8")

    report, payload = _report_for(tmp_path)
    posix = relative.replace("\\", "/")
    expected_message = (
        f"Hard-coded secret-like value in test/example file {posix}:1"
    )

    assert payload["risk_map"]["critical"] == []
    assert payload["risk_map"]["warning"][0]["message"] == expected_message
    assert payload["risk_map"]["warning"][0]["confidence"] == "MEDIUM"
    assert expected_message in report
    assert "rotate" not in report.lower()
    assert (
        f"Confirm the secret-like value in {posix} (line 1) "
        "is a test fixture, not a live credential."
    ) in payload["checklist"]


def test_mixed_repo_splits_severity_and_lists_production_first(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "config.py").write_text(SECRET_LINE, encoding="utf-8")
    (tmp_path / "tests" / "config.py").write_text(SECRET_LINE, encoding="utf-8")

    report, payload = _report_for(tmp_path)

    assert payload["summary"]["risks_count"] == 2
    assert payload["risk_map"]["critical"] == [
        {"message": "Hard-coded secret in config.py:1", "confidence": "MEDIUM"}
    ]
    assert payload["risk_map"]["warning"] == [
        {
            "message": (
                "Hard-coded secret-like value in test/example file tests/config.py:1"
            ),
            "confidence": "MEDIUM",
        }
    ]
    rotate = "Review and rotate hard-coded credentials in config.py (line 1)."
    confirm = (
        "Confirm the secret-like value in tests/config.py (line 1) "
        "is a test fixture, not a live credential."
    )
    assert payload["checklist"].index(rotate) < payload["checklist"].index(confirm)
    assert rotate in report
    assert confirm in report


def test_test_only_secrets_are_warnings_and_yellow_badge(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "config.py").write_text(SECRET_LINE, encoding="utf-8")

    report, payload = _report_for(tmp_path)

    assert payload["risk_map"]["critical"] == []
    assert len(payload["risk_map"]["warning"]) == 1
    assert "no major risks" not in report
    critical_block = report.split("### [CRITICAL]", 1)[1].split("### [WARNING]", 1)[0]
    assert "Hard-coded secret in " not in critical_block
    assert "- None detected." in critical_block
    assert "1%20risks-yellow" in payload["summary"]["badge_url"]
    assert "critical-red" not in payload["summary"]["badge_url"]


def test_contest_and_test_utils_stay_critical(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    contest = tmp_path / "contest"
    contest.mkdir()
    (contest / "app.py").write_text(SECRET_LINE, encoding="utf-8")
    src = tmp_path / "src"
    src.mkdir()
    (src / "test_utils.py").write_text(SECRET_LINE, encoding="utf-8")

    _, payload = _report_for(tmp_path)
    critical_messages = [item["message"] for item in payload["risk_map"]["critical"]]

    assert "Hard-coded secret in contest/app.py:1" in critical_messages
    assert "Hard-coded secret in src/test_utils.py:1" in critical_messages
    assert payload["risk_map"]["warning"] == []


def test_default_min_confidence_hides_todo_info(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "app.py").write_text(TODO_LINE, encoding="utf-8")

    report, payload = _report_for(tmp_path, min_confidence=Confidence.MEDIUM)

    assert payload["risk_map"]["info"] == []
    assert "TODO in app.py:1" not in report


def test_low_min_confidence_includes_todo_info(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "app.py").write_text(TODO_LINE, encoding="utf-8")

    report, payload = _report_for(tmp_path, min_confidence=Confidence.LOW)

    assert payload["risk_map"]["info"] == [
        {"message": "TODO in app.py:1", "confidence": "LOW"}
    ]
    assert "TODO in app.py:1" in report


def test_report_title_resolves_dot_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "my-app"
    repo.mkdir()
    monkeypatch.chdir(repo)
    stack, _, git_log, risks = make_report_data()
    risks = {
        "missing_tests": False,
        "markers": [],
        "secrets": [],
        "dependency_conflicts": [],
    }
    generator = ReportGenerator(".", stack, {}, git_log, risks)

    assert "# REBRIEF REPORT: my-app" in generator.generate()


def test_overview_uses_project_context_files_label(tmp_path: Path) -> None:
    stack, rules, git_log, risks = make_report_data()
    generator = ReportGenerator(str(tmp_path / "demo-repo"), stack, rules, git_log, risks)
    report = generator.generate()

    assert "Project context files found: 2 (.cursorrules, CLAUDE.md)." in report
    assert "AI instruction files" not in report


def test_this_repo_fixture_secrets_are_warnings_not_critical() -> None:
    risks = RisksParser(str(REPO_ROOT)).parse()
    generator = ReportGenerator(
        str(REPO_ROOT),
        _empty_stack(),
        {},
        _empty_git(),
        risks,
    )
    payload = generator.to_dict()
    report = generator.generate()

    fixture_paths = (
        "tests/fixtures/secrets/aws_config.py",
        "tests/test_confidence.py",
    )
    warning_messages = [item["message"] for item in payload["risk_map"]["warning"]]
    critical_messages = [item["message"] for item in payload["risk_map"]["critical"]]

    for relative in fixture_paths:
        assert any(relative in message for message in warning_messages)
        assert all(relative not in message for message in critical_messages)
        assert f"test/example file {relative}" in report
        assert (
            f"Confirm the secret-like value in {relative}" in "\n".join(payload["checklist"])
        )
        assert (
            f"Review and rotate hard-coded credentials in {relative}"
            not in payload["checklist"]
        )
