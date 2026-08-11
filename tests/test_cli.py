from pathlib import Path

from click.testing import CliRunner

from rebrief import __version__
from rebrief.cli import main
from rebrief.core.ignore import REBRIEFIGNORE_FILENAME


def test_main_help() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "Audit AI-generated repositories" in result.output


def test_main_version() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_init_creates_rebriefignore(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["init", str(tmp_path)])

    assert result.exit_code == 0
    assert "Created" in result.output
    assert (tmp_path / REBRIEFIGNORE_FILENAME).is_file()


def test_init_existing_file_no_overwrite(tmp_path: Path) -> None:
    ignore_path = tmp_path / REBRIEFIGNORE_FILENAME
    ignore_path.write_text("custom/\n", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(main, ["init", str(tmp_path)])

    assert result.exit_code == 0
    assert "already exists" in result.output
    assert ignore_path.read_text(encoding="utf-8") == "custom/\n"


def test_scan_creates_rebriefignore_on_first_run(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_app.py").write_text("def test_ok() -> None:\n    pass\n", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(main, ["scan", str(tmp_path)])

    assert result.exit_code == 0
    assert (tmp_path / REBRIEFIGNORE_FILENAME).is_file()
    assert "Created .rebriefignore" in result.output


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
    assert (tmp_path / REBRIEFIGNORE_FILENAME).is_file()
    report = (tmp_path / "REBRIEF.md").read_text(encoding="utf-8")
    assert "Empty repository detected." not in report
    assert "Add a `tests/` directory" in report


def test_scan_no_git_folder(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Demo\n", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(main, ["scan", str(tmp_path)])

    assert result.exit_code == 0
    report = (tmp_path / "REBRIEF.md").read_text(encoding="utf-8")
    assert "No commits detected yet. Repository is at point zero." in report
