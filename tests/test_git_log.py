import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

from rebrief.parsers.git_log import POINT_ZERO_MESSAGE, GitLogParser


def _mock_run_side_effect(log_stdout: str, churn_stdout: str) -> MagicMock:
    def side_effect(cmd: list[str], **kwargs: object) -> MagicMock:
        result = MagicMock()
        result.stdout = churn_stdout if "--name-only" in cmd else log_stdout
        result.returncode = 0
        return result

    return side_effect


def test_missing_git_returns_empty(tmp_path: Path) -> None:
    result = GitLogParser(str(tmp_path)).parse()

    assert result == {
        "commits": [],
        "top_modified_files": [],
        "status_message": POINT_ZERO_MESSAGE,
    }


@patch("rebrief.parsers.git_log.subprocess.run")
def test_parses_meaningful_commits(mock_run: MagicMock, tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    log_stdout = "\n".join(
        [
            "a1b2c3d|Alice|2026-01-15|Add authentication module",
            "d4e5f6g|Bob|2026-01-14|Implement user registration",
            "h7i8j9k|Carol|2026-01-13|Design database schema",
        ]
    )
    mock_run.side_effect = _mock_run_side_effect(log_stdout, "")

    result = GitLogParser(str(tmp_path)).parse()

    assert len(result["commits"]) == 3
    assert result["commits"][0] == {
        "hash": "a1b2c3d",
        "author": "Alice",
        "date": "2026-01-15",
        "subject": "Add authentication module",
    }
    assert result["status_message"] is None


@patch("rebrief.parsers.git_log.subprocess.run")
def test_filters_noisy_commits(mock_run: MagicMock, tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    log_stdout = "\n".join(
        [
            "1111111|Alice|2026-01-15|wip",
            "2222222|Bob|2026-01-14|fix typo in readme",
            "3333333|Carol|2026-01-13|refactor stuff",
            "4444444|Dave|2026-01-12|Add payment gateway",
        ]
    )
    mock_run.side_effect = _mock_run_side_effect(log_stdout, "")

    result = GitLogParser(str(tmp_path)).parse()

    assert len(result["commits"]) == 1
    assert result["commits"][0]["subject"] == "Add payment gateway"


@patch("rebrief.parsers.git_log.subprocess.run")
def test_limits_to_25_commits(mock_run: MagicMock, tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    log_stdout = "\n".join(
        f"{index:07d}|Author|2026-01-01|Meaningful commit {index}"
        for index in range(40)
    )
    mock_run.side_effect = _mock_run_side_effect(log_stdout, "")

    result = GitLogParser(str(tmp_path)).parse()

    assert len(result["commits"]) == 25


@patch("rebrief.parsers.git_log.subprocess.run")
def test_parses_top_modified_files(mock_run: MagicMock, tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    churn_stdout = "\n".join(
        [
            "src/app.py",
            "src/app.py",
            "README.md",
            "",
            "src/app.py",
            "src/utils.py",
            "src/utils.py",
            "src/utils.py",
            "tests/test_app.py",
            "tests/test_app.py",
            "docs/guide.md",
        ]
    )
    mock_run.side_effect = _mock_run_side_effect("", churn_stdout)

    result = GitLogParser(str(tmp_path)).parse()

    assert result["top_modified_files"] == [
        {"file": "src/app.py", "count": 3},
        {"file": "src/utils.py", "count": 3},
        {"file": "tests/test_app.py", "count": 2},
        {"file": "README.md", "count": 1},
        {"file": "docs/guide.md", "count": 1},
    ]


@patch("rebrief.parsers.git_log.subprocess.run")
def test_git_failure_returns_empty(mock_run: MagicMock, tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    mock_run.side_effect = FileNotFoundError("git not found")

    result = GitLogParser(str(tmp_path)).parse()

    assert result == {
        "commits": [],
        "top_modified_files": [],
        "status_message": POINT_ZERO_MESSAGE,
    }


@patch("rebrief.parsers.git_log.subprocess.run")
def test_git_nonzero_exit_returns_empty(mock_run: MagicMock, tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    mock_run.side_effect = subprocess.CalledProcessError(128, "git")

    result = GitLogParser(str(tmp_path)).parse()

    assert result == {
        "commits": [],
        "top_modified_files": [],
        "status_message": POINT_ZERO_MESSAGE,
    }


def test_git_init_no_commits_returns_point_zero_message(tmp_path: Path) -> None:
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)

    result = GitLogParser(str(tmp_path)).parse()

    assert result["commits"] == []
    assert result["top_modified_files"] == []
    assert result["status_message"] == POINT_ZERO_MESSAGE
