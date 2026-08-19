from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from rebrief.cli import main
from rebrief.core.reporter import ReportGenerator
from rebrief.parsers.ownership import (
    OwnershipParser,
    classify_expertise,
    detect_ai_tools_in_text,
    format_ownership_table,
    format_secondary_display,
    is_ai_author,
    module_key_for_path,
)
from tests.test_reporter import make_report_data


def _git(tmp_path: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)


def _init_repo(tmp_path: Path) -> None:
    _git(tmp_path, "init", "-b", "main")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test User")


def test_module_key_for_path() -> None:
    assert module_key_for_path("main.py") == "."
    assert module_key_for_path("src/app.py") == "src/"
    assert module_key_for_path("apps/backend/main.py") == "apps/backend/"
    assert module_key_for_path("packages/db/models.py") == "packages/db/"


def test_detect_ai_tools_in_text() -> None:
    message = (
        "Add auth module\n\n"
        "Co-authored-by: Claude <noreply@anthropic.com>\n"
    )
    assert detect_ai_tools_in_text(message) == ["Claude"]

    assert "Cursor" in detect_ai_tools_in_text("Refactor with Cursor agent")
    assert detect_ai_tools_in_text("Fix typo") == []


def test_is_ai_author() -> None:
    assert is_ai_author("Alice", "alice@example.com") == []
    assert "Copilot" in is_ai_author("GitHub Copilot", "copilot@github.com")
    assert "Claude" in is_ai_author("Claude", "noreply@anthropic.com")


def test_classify_expertise() -> None:
    assert classify_expertise(primary_percent=80, line_count=500, recent_churn=5) == (
        "High Activity"
    )
    assert classify_expertise(primary_percent=80, line_count=500, recent_churn=0) == (
        "Stable / Maintenance"
    )
    assert classify_expertise(primary_percent=40, line_count=500, recent_churn=1) == (
        "Shared"
    )
    assert classify_expertise(primary_percent=90, line_count=10, recent_churn=0) == (
        "Low Activity"
    )


def test_format_secondary_display_ai_assisted() -> None:
    text = format_secondary_display(
        secondary="",
        secondary_percent=0.0,
        ai_assisted=True,
        ai_percent=75.0,
        ai_tools=["Cursor", "Claude"],
    )
    assert "AI-Assisted" in text
    assert "75%" in text
    assert "Cursor/Claude" in text


def test_format_ownership_table() -> None:
    modules = {
        "apps/backend/": {
            "contributors": {"Alex": 65.0, "Claude Agent": 35.0},
            "primary_owner": "Alex",
            "primary_percent": 65.0,
            "secondary": "Claude Agent",
            "secondary_percent": 35.0,
            "ai_assisted": True,
            "ai_percent": 35.0,
            "ai_tools": ["Claude"],
            "expertise_level": "High Activity",
            "rapid_ai_session": False,
            "line_count": 100,
        }
    }
    lines = format_ownership_table(modules)
    assert "| Module / Path | Primary Owner | Secondary / AI Contributor |" in lines[0]
    assert "`apps/backend/`" in lines[2]
    assert "Alex (65%)" in lines[2]
    assert "High Activity" in lines[2]


def test_blame_file_parses_porcelain_header() -> None:
    parser = OwnershipParser(".")
    output = (
        "a" * 40 + " 1 1 1\n"
        "author Alice\n"
        "author-mail <alice@example.com>\n"
        "\tprint('hi')\n"
    )

    with patch.object(parser, "_run_git", return_value=output):
        results = parser._blame_file("src/app.py")

    assert results == [("Alice", "a" * 40)]


def test_blame_file_ignores_bare_sha_line_without_trailing_fields() -> None:
    """A 40-char hex-only line must not raise IndexError."""
    parser = OwnershipParser(".")
    output = (
        "a" * 40 + "\n"
        "author Bob\n"
        "\tcode\n"
    )

    with patch.object(parser, "_run_git", return_value=output):
        results = parser._blame_file("src/app.py")

    assert results == []


def test_parse_skipped_when_no_blame(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    result = OwnershipParser(str(tmp_path), skip=True).parse()
    assert result["skipped"] is True
    assert result["modules"] == {}
    assert result["skip_reason"] == "disabled via --no-blame"


def test_parse_missing_git_returns_empty(tmp_path: Path) -> None:
    result = OwnershipParser(str(tmp_path)).parse()
    assert result["modules"] == {}
    assert result["skipped"] is False


def test_collect_blame_files_excludes_tests(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("print('ok')\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_app.py").write_text("def test_ok() -> None: pass\n", encoding="utf-8")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "guide.md").write_text("# Guide\n", encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "Initial import")

    parser = OwnershipParser(str(tmp_path))
    files = parser._collect_blame_files()
    assert "src/app.py" in files
    assert "tests/test_app.py" not in files
    assert "docs/guide.md" not in files


def test_synthetic_git_repo_ownership(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    backend = tmp_path / "apps" / "backend"
    backend.mkdir(parents=True)
    db = tmp_path / "packages" / "db"
    db.mkdir(parents=True)

    (backend / "main.py").write_text("print('backend')\n" * 5, encoding="utf-8")
    _git(tmp_path, "config", "user.name", "Alex")
    _git(tmp_path, "config", "user.email", "alex@example.com")
    _git(tmp_path, "add", "apps/backend/main.py")
    _git(tmp_path, "commit", "-m", "Add backend service")

    (db / "models.py").write_text("class User: pass\n" * 5, encoding="utf-8")
    _git(tmp_path, "config", "user.name", "Aidar")
    _git(tmp_path, "config", "user.email", "aidar@example.com")
    _git(tmp_path, "add", "packages/db/models.py")
    _git(tmp_path, "commit", "-m", "Add database models")

    (backend / "routes.py").write_text("def route() -> None: pass\n" * 5, encoding="utf-8")
    _git(tmp_path, "config", "user.name", "Alex")
    _git(tmp_path, "config", "user.email", "alex@example.com")
    _git(tmp_path, "add", "apps/backend/routes.py")
    _git(
        tmp_path,
        "commit",
        "-m",
        "Add routes\n\nCo-authored-by: Claude <noreply@anthropic.com>",
    )

    result = OwnershipParser(str(tmp_path)).parse()
    modules = result["modules"]

    assert "apps/backend/" in modules
    assert "packages/db/" in modules
    assert modules["packages/db/"]["primary_owner"] == "Aidar"
    assert modules["apps/backend/"]["primary_owner"] == "Alex"
    assert modules["apps/backend/"]["ai_assisted"] is True
    assert "Claude" in modules["apps/backend/"]["ai_tools"]


def test_reporter_ownership_section(tmp_path: Path) -> None:
    stack, rules, git_log, risks = make_report_data()
    ownership = {
        "modules": {
            "apps/backend/": {
                "contributors": {"Alex": 65.0, "Claude Agent": 35.0},
                "primary_owner": "Alex",
                "primary_percent": 65.0,
                "secondary": "Claude Agent",
                "secondary_percent": 35.0,
                "ai_assisted": True,
                "ai_percent": 35.0,
                "ai_tools": ["Claude"],
                "expertise_level": "High Activity",
                "rapid_ai_session": False,
                "line_count": 120,
            }
        },
        "skipped": False,
        "skip_reason": None,
    }
    generator = ReportGenerator(
        str(tmp_path / "demo-repo"),
        stack,
        rules,
        git_log,
        risks,
        ownership=ownership,
    )
    report = generator.generate()

    assert "### 👥 Code Ownership & Expertise Map" in report
    assert "`apps/backend/`" in report
    assert "Alex (65%)" in report
    assert "High Activity" in report

    payload = generator.to_dict()
    assert "apps/backend/" in payload["ownership_map"]
    assert payload["ownership_map"]["apps/backend/"]["ai_assisted"] is True


def test_reporter_no_blame_note(tmp_path: Path) -> None:
    stack, rules, git_log, risks = make_report_data()
    generator = ReportGenerator(
        str(tmp_path / "demo-repo"),
        stack,
        rules,
        git_log,
        risks,
        no_blame=True,
    )
    report = generator.generate()
    assert "### 👥 Code Ownership & Expertise Map" in report
    assert "--no-blame" in report
    assert generator.to_dict()["ownership_map"] == {}


@patch("rebrief.parsers.ownership.subprocess.run")
def test_parse_handles_git_failure(mock_run: MagicMock, tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    mock_run.side_effect = subprocess.CalledProcessError(128, "git")
    result = OwnershipParser(str(tmp_path)).parse()
    assert result["modules"] == {}


def test_scan_no_blame_flag(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("print('ok')\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_app.py").write_text("def test_ok() -> None: pass\n", encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "Initial import")

    runner = CliRunner()
    md_result = runner.invoke(main, ["scan", str(tmp_path), "--no-blame", "-y"])
    assert md_result.exit_code == 0
    report = (tmp_path / "REBRIEF.md").read_text(encoding="utf-8")
    assert "--no-blame" in report

    json_result = runner.invoke(
        main, ["scan", str(tmp_path), "--no-blame", "-f", "json", "-y"]
    )
    assert json_result.exit_code == 0

    import json

    payload = json.loads((tmp_path / "REBRIEF.json").read_text(encoding="utf-8"))
    assert payload["ownership_map"] == {}
