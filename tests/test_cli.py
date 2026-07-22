from pathlib import Path

from click.testing import CliRunner

from rebrief.cli import main


def test_main_help() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "Audit AI-generated repositories" in result.output


def test_main_version() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["--version"])
    assert result.exit_code == 0
    assert "0.1.1" in result.output


def test_scan(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_app.py").write_text("def test_ok() -> None:\n    pass\n", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(main, ["scan", str(tmp_path)])

    assert result.exit_code == 0
    assert "Scanning repository" in result.output
    assert "Languages found" in result.output
    assert "Risks identified" in result.output
    assert "Scan complete" in result.output
    assert (tmp_path / "REBRIEF.md").is_file()


def test_scan_empty_folder(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["scan", str(tmp_path)])

    assert result.exit_code == 0
    report = (tmp_path / "REBRIEF.md").read_text(encoding="utf-8")
    assert "Empty repository detected." in report


def test_scan_no_git_folder(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Demo\n", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(main, ["scan", str(tmp_path)])

    assert result.exit_code == 0
    report = (tmp_path / "REBRIEF.md").read_text(encoding="utf-8")
    assert "No commits detected yet. Repository is at point zero." in report
