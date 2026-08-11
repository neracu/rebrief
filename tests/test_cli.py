from pathlib import Path
import json

from click.testing import CliRunner

from rebrief import __version__
from rebrief.cli import main
from rebrief.core.ignore import REBRIEFIGNORE_FILENAME


def test_main_help() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "Audit AI-generated repositories" in result.output


def test_scan_help() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["scan", "--help"])
    assert result.exit_code == 0
    assert "--format" in result.output
    assert "--output" in result.output
    assert "--min-confidence" in result.output
    assert "-c" in result.output
    assert "--inject-badge" in result.output


def test_badge_help() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["badge", "--help"])
    assert result.exit_code == 0
    assert "--min-confidence" in result.output
    assert "Shields.io" in result.output or "badge" in result.output.lower()


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


def test_scan_format_json_default_output(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_app.py").write_text("def test_ok() -> None:\n    pass\n", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(main, ["scan", str(tmp_path), "--format", "json"])

    assert result.exit_code == 0
    assert (tmp_path / "REBRIEF.json").is_file()
    assert not (tmp_path / "REBRIEF.md").is_file()


def test_scan_format_json_custom_output(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_app.py").write_text("def test_ok() -> None:\n    pass\n", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["scan", str(tmp_path), "-f", "json", "-o", "report.json"],
    )

    assert result.exit_code == 0
    assert (tmp_path / "report.json").is_file()


def test_scan_stdout_json(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_app.py").write_text("def test_ok() -> None:\n    pass\n", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(main, ["scan", str(tmp_path), "-f", "json", "-o", "-"])

    assert result.exit_code == 0
    assert not (tmp_path / "REBRIEF.json").is_file()
    json_start = result.output.find("{")
    assert json_start >= 0
    payload = json.loads(result.output[json_start:])
    assert "version" in payload
    assert "tech_stack" in payload


def test_scan_stdout_markdown(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_app.py").write_text("def test_ok() -> None:\n    pass\n", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(main, ["scan", str(tmp_path), "-o", "-"])

    assert result.exit_code == 0
    assert not (tmp_path / "REBRIEF.md").is_file()
    assert "# REBRIEF REPORT:" in result.output


def test_scan_min_confidence_filters_low_markers(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("# TODO review later\n", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(main, ["scan", str(tmp_path), "-c", "medium"])

    assert result.exit_code == 0
    report = (tmp_path / "REBRIEF.md").read_text(encoding="utf-8")
    assert "Missing tests directory" in report
    assert "TODO in app.py:1" not in report
    assert "Risks identified    1" in result.output


def test_scan_min_confidence_low_includes_markers(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("# TODO review later\n", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(main, ["scan", str(tmp_path), "-c", "low"])

    assert result.exit_code == 0
    report = (tmp_path / "REBRIEF.md").read_text(encoding="utf-8")
    assert "TODO in app.py:1" in report
    assert "Risks identified    2" in result.output


def test_badge_prints_markdown_and_html(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_app.py").write_text(
        "def test_ok() -> None:\n    pass\n", encoding="utf-8"
    )

    runner = CliRunner()
    result = runner.invoke(main, ["badge", str(tmp_path)])

    assert result.exit_code == 0
    assert "[![Rebrief](https://img.shields.io/badge/rebrief-" in result.output
    assert '<a href="https://github.com/neracu/rebrief">' in result.output
    assert '<img alt="Rebrief"' in result.output


def test_scan_inject_badge_under_header(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "# Demo\n\nBody text stays.\n", encoding="utf-8"
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_app.py").write_text(
        "def test_ok() -> None:\n    pass\n", encoding="utf-8"
    )

    runner = CliRunner()
    result = runner.invoke(main, ["scan", str(tmp_path), "--inject-badge"])

    assert result.exit_code == 0
    readme = (tmp_path / "README.md").read_text(encoding="utf-8")
    assert "<!-- REBRIEF-BADGE:START -->" in readme
    assert "<!-- REBRIEF-BADGE:END -->" in readme
    assert "[![Rebrief](https://img.shields.io/badge/rebrief-" in readme
    assert "Body text stays." in readme
    assert readme.index("# Demo") < readme.index("<!-- REBRIEF-BADGE:START -->")
    assert "Badge injected" in result.output


def test_scan_inject_badge_replaces_existing_markers(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "# Demo\n"
        "\n"
        "Before.\n"
        "\n"
        "<!-- REBRIEF-BADGE:START -->\n"
        "[![Rebrief](https://img.shields.io/badge/rebrief-clean-brightgreen)]"
        "(https://github.com/neracu/rebrief)\n"
        "<!-- REBRIEF-BADGE:END -->\n"
        "\n"
        "After.\n",
        encoding="utf-8",
    )
    # Force a warning risk (missing tests) so badge is yellow, not clean
    runner = CliRunner()
    result = runner.invoke(main, ["scan", str(tmp_path), "--inject-badge"])

    assert result.exit_code == 0
    readme = (tmp_path / "README.md").read_text(encoding="utf-8")
    assert "Before." in readme
    assert "After." in readme
    assert readme.count("<!-- REBRIEF-BADGE:START -->") == 1
    assert "rebrief-clean-brightgreen" not in readme
    assert "rebrief-" in readme
