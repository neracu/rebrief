from pathlib import Path
import json
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from rebrief import __version__
from rebrief.cli import main
from rebrief.core.ignore import REBRIEFIGNORE_FILENAME
from rebrief.core.remote import CLONE_ERROR_MESSAGE, RemoteCloneError


def test_main_help() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "Audit AI-generated repositories" in result.output


def test_scan_help() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["scan", "--help"])
    assert result.exit_code == 0
    assert "TARGET" in result.output
    assert "--format" in result.output
    assert "--output" in result.output
    assert "--min-confidence" in result.output
    assert "-c" in result.output
    assert "--inject-badge" in result.output
    assert "--diff" in result.output
    assert "--plain" in result.output
    assert "--no-color" in result.output
    assert "--yes" in result.output
    assert "-y" in result.output


def test_badge_help() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["badge", "--help"])
    assert result.exit_code == 0
    assert "--min-confidence" in result.output
    assert "Shields.io" in result.output or "badge" in result.output.lower()


def test_serve_help() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["serve", "--help"])
    assert result.exit_code == 0
    assert "--host" in result.output
    assert "--port" in result.output
    assert "--open" in result.output
    assert "--no-open" in result.output


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
    assert "[1/4] Parsing repository manifests & tech stack..." in result.output
    assert "[2/4] Analyzing git history & hotspots..." in result.output
    assert "[3/4] Running risk detectors & confidence checks..." in result.output
    assert "[4/4] Calculating token metrics & generating report..." in result.output
    assert "Tech Stack" in result.output
    assert "Languages" in result.output
    assert "Token Savings" in result.output
    assert "saved to" in result.output
    assert "token savings" in result.output
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


def test_scan_format_xml_default_output(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_app.py").write_text("def test_ok() -> None:\n    pass\n", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(main, ["scan", str(tmp_path), "--format", "xml"])

    assert result.exit_code == 0
    assert (tmp_path / "REBRIEF.xml").is_file()
    assert not (tmp_path / "REBRIEF.md").is_file()
    xml_text = (tmp_path / "REBRIEF.xml").read_text(encoding="utf-8")
    assert xml_text.startswith('<?xml version="1.0" encoding="UTF-8"?>')
    assert "<rebrief " in xml_text


def test_scan_format_xml_custom_output(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_app.py").write_text("def test_ok() -> None:\n    pass\n", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["scan", str(tmp_path), "-f", "xml", "-o", "report.xml"],
    )

    assert result.exit_code == 0
    assert (tmp_path / "report.xml").is_file()


def test_scan_stdout_xml(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_app.py").write_text("def test_ok() -> None:\n    pass\n", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(main, ["scan", str(tmp_path), "-f", "xml", "-o", "-"])

    assert result.exit_code == 0
    assert not (tmp_path / "REBRIEF.xml").is_file()
    xml_start = result.output.find("<?xml")
    assert xml_start >= 0
    xml_text = result.output[xml_start:]
    assert "<rebrief " in xml_text
    assert "<summary>" in xml_text
    assert "<tech_stack>" in xml_text


def test_scan_format_html_default_output(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_app.py").write_text("def test_ok() -> None:\n    pass\n", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(main, ["scan", str(tmp_path), "--format", "html"])

    assert result.exit_code == 0
    html_path = tmp_path / "REBRIEF.html"
    assert html_path.is_file()
    assert not (tmp_path / "REBRIEF.md").is_file()
    html = html_path.read_text(encoding="utf-8")
    assert html.startswith("<!DOCTYPE html>")
    assert "<style>" in html
    assert "<script>" in html
    assert html.strip()


def test_scan_format_html_custom_output(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_app.py").write_text("def test_ok() -> None:\n    pass\n", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["scan", str(tmp_path), "-f", "html", "-o", "report.html"],
    )

    assert result.exit_code == 0
    assert (tmp_path / "report.html").is_file()


def test_scan_stdout_html(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_app.py").write_text("def test_ok() -> None:\n    pass\n", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(main, ["scan", str(tmp_path), "-f", "html", "-o", "-"])

    assert result.exit_code == 0
    assert not (tmp_path / "REBRIEF.html").is_file()
    html_start = result.output.find("<!DOCTYPE html>")
    assert html_start >= 0
    html = result.output[html_start:]
    assert "<style>" in html
    assert "<script>" in html
    assert "Token efficiency" in html


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
    token_stats = payload["summary"]["token_stats"]
    assert set(token_stats) == {
        "raw_codebase_tokens",
        "brief_tokens",
        "savings_percentage",
        "tokenizer",
    }
    assert token_stats["raw_codebase_tokens"] >= 0
    assert token_stats["brief_tokens"] > 0


def test_scan_stdout_markdown(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_app.py").write_text("def test_ok() -> None:\n    pass\n", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(main, ["scan", str(tmp_path), "-o", "-"])

    assert result.exit_code == 0
    assert not (tmp_path / "REBRIEF.md").is_file()
    assert "# REBRIEF REPORT:" in result.output
    assert "Token Savings:" in result.output


def test_scan_plain_omits_banner_and_ansi(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_app.py").write_text(
        "def test_ok() -> None:\n    pass\n", encoding="utf-8"
    )

    runner = CliRunner()
    result = runner.invoke(main, ["scan", str(tmp_path), "--plain"])

    assert result.exit_code == 0, result.output
    assert (tmp_path / "REBRIEF.md").is_file()
    assert "\x1b[" not in result.output
    assert "⚡" not in result.output
    from rebrief.ui import BANNER_ART

    assert BANNER_ART.split("\n")[0] not in result.output
    assert "Token-Efficient Codebase Briefings for AI Agents" in result.output
    assert "saved to" in result.output


def test_scan_no_color_alias(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_app.py").write_text(
        "def test_ok() -> None:\n    pass\n", encoding="utf-8"
    )

    runner = CliRunner()
    result = runner.invoke(main, ["scan", str(tmp_path), "--no-color"])

    assert result.exit_code == 0, result.output
    assert "\x1b[" not in result.output
    assert (tmp_path / "REBRIEF.md").is_file()


def test_scan_settings_quit_does_not_write_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from rebrief.ui import ScanUI

    monkeypatch.setattr(ScanUI, "should_prompt_settings", lambda self, **kwargs: True)
    monkeypatch.setattr(ScanUI, "prompt_settings", lambda self, settings, **kwargs: None)

    runner = CliRunner()
    result = runner.invoke(main, ["scan", str(tmp_path)])

    assert result.exit_code == 0
    assert not (tmp_path / "REBRIEF.md").exists()


def test_scan_settings_start_can_switch_to_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from rebrief.ui import ScanSettings, ScanUI

    def fake_prompt(self: ScanUI, settings: ScanSettings, **kwargs: object) -> ScanSettings:
        settings.apply_format("json")
        return settings

    monkeypatch.setattr(ScanUI, "should_prompt_settings", lambda self, **kwargs: True)
    monkeypatch.setattr(ScanUI, "prompt_settings", fake_prompt)

    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_app.py").write_text(
        "def test_ok() -> None:\n    pass\n", encoding="utf-8"
    )
    runner = CliRunner()
    result = runner.invoke(main, ["scan", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert (tmp_path / "REBRIEF.json").is_file()
    assert not (tmp_path / "REBRIEF.md").exists()


def test_scan_stdout_json_ui_on_stderr(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_app.py").write_text(
        "def test_ok() -> None:\n    pass\n", encoding="utf-8"
    )

    runner = CliRunner()
    result = runner.invoke(main, ["scan", str(tmp_path), "-f", "json", "-o", "-"])

    assert result.exit_code == 0, result.output
    stdout = result.stdout if hasattr(result, "stdout") else result.output
    start = stdout.find("{")
    end = stdout.rfind("}")
    assert start >= 0 and end > start
    payload = json.loads(stdout[start : end + 1])
    assert "tech_stack" in payload

    ui_text = result.output
    stderr = getattr(result, "stderr", None)
    if stderr:
        ui_text = stderr
        assert "[1/4]" not in stdout[:start]
    assert "[1/4]" in ui_text or "[1/4]" in result.output
    assert "saved to" in ui_text or "saved to" in result.output


def test_scan_min_confidence_filters_low_markers(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("# TODO review later\n", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(main, ["scan", str(tmp_path), "-c", "medium"])

    assert result.exit_code == 0
    report = (tmp_path / "REBRIEF.md").read_text(encoding="utf-8")
    assert "Missing tests directory" in report
    assert "TODO in app.py:1" not in report
    assert "TODO in app.py:1" not in result.output
    assert "WARNING" in result.output


def test_scan_min_confidence_low_includes_markers(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("# TODO review later\n", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(main, ["scan", str(tmp_path), "-c", "low"])

    assert result.exit_code == 0
    report = (tmp_path / "REBRIEF.md").read_text(encoding="utf-8")
    assert "TODO in app.py:1" in report
    assert "TODO in app.py:1" in result.output
    assert "NEEDS_VERIFICATION" in result.output


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


def _init_git_repo(tmp_path: Path) -> None:
    import subprocess

    subprocess.run(
        ["git", "init"], cwd=tmp_path, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "checkout", "-b", "main"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )


def test_scan_diff_mode_json(tmp_path: Path) -> None:
    import subprocess

    _init_git_repo(tmp_path)
    (tmp_path / "tests").mkdir()
    (tmp_path / "a.py").write_text("print(1)\n", encoding="utf-8")
    subprocess.run(
        ["git", "add", "."], cwd=tmp_path, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "commit", "-m", "Initial"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    (tmp_path / "b.py").write_text("# TODO: ship it\n", encoding="utf-8")
    subprocess.run(
        ["git", "add", "b.py"], cwd=tmp_path, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "commit", "-m", "Add b"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )

    runner = CliRunner()
    result = runner.invoke(
        main, ["scan", str(tmp_path), "--diff", "-f", "json", "-o", "-"]
    )

    assert result.exit_code == 0, result.output
    json_start = result.output.find("{")
    assert json_start != -1
    payload = json.loads(result.output[json_start:])
    assert payload["mode"] == "incremental"
    assert payload["diff_ref"] == "HEAD~1"
    assert payload["summary"]["files_scanned"] == 1
    assert payload["summary"]["files_total"] == 2


def test_scan_diff_not_a_git_repo(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["scan", str(tmp_path), "--diff"])

    assert result.exit_code == 1
    assert "Not a git repository" in result.output


def _seed_cloned_repo(dest: Path) -> None:
    (dest / "tests").mkdir()
    (dest / "tests" / "test_app.py").write_text(
        "def test_ok() -> None:\n    pass\n", encoding="utf-8"
    )
    (dest / "README.md").write_text("# demo\n", encoding="utf-8")


def test_scan_remote_writes_to_cwd() -> None:
    cloned: dict[str, Path] = {}

    def fake_clone(url: str, dest: Path, **kwargs: object) -> None:
        cloned["dest"] = dest
        _seed_cloned_repo(dest)

    runner = CliRunner()
    with patch("rebrief.core.remote.clone_remote", fake_clone):
        with runner.isolated_filesystem():
            result = runner.invoke(main, ["scan", "owner/repo"])
            assert result.exit_code == 0, result.output
            assert Path("REBRIEF.md").is_file()
            assert "Fetching remote repository [owner/repo]" in result.output
            assert cloned["dest"] not in (Path("REBRIEF.md").resolve().parents)

    assert "dest" in cloned
    assert not cloned["dest"].exists()


def test_scan_remote_clone_failure() -> None:
    def boom(url: str, dest: Path, **kwargs: object) -> None:
        raise RemoteCloneError(CLONE_ERROR_MESSAGE)

    runner = CliRunner()
    with patch("rebrief.core.remote.clone_remote", boom):
        result = runner.invoke(main, ["scan", "https://github.com/owner/repo"])
    assert result.exit_code == 1
    assert "Unable to access remote repository" in result.output
    assert "authentication credentials" in result.output


def test_scan_remote_ignores_inject_badge() -> None:
    def fake_clone(url: str, dest: Path, **kwargs: object) -> None:
        _seed_cloned_repo(dest)

    runner = CliRunner()
    with patch("rebrief.core.remote.clone_remote", fake_clone):
        with runner.isolated_filesystem():
            result = runner.invoke(main, ["scan", "owner/repo", "--inject-badge"])
            assert result.exit_code == 0, result.output
            assert "--inject-badge is ignored" in result.output
            assert Path("REBRIEF.md").is_file()


def test_scan_missing_local_path() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["scan", "not-a-directory"])
    assert result.exit_code == 1
    assert "does not exist" in result.output


def test_scan_local_owner_repo_dir_not_cloned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "owner" / "repo"
    repo.mkdir(parents=True)
    (repo / "tests").mkdir()
    (repo / "tests" / "test_app.py").write_text(
        "def test_ok() -> None:\n    pass\n", encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)

    def fail_clone(url: str, dest: Path) -> None:
        raise AssertionError("local owner/repo should not be cloned")

    runner = CliRunner()
    with patch("rebrief.core.remote.clone_remote", fail_clone):
        result = runner.invoke(main, ["scan", "owner/repo"])
    assert result.exit_code == 0, result.output
    assert (repo / "REBRIEF.md").is_file()
    assert not (tmp_path / "REBRIEF.md").exists()


def test_main_help_lists_mcp() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "mcp" in result.output
    assert "server" in result.output


def test_mcp_help() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["mcp", "--help"])
    assert result.exit_code == 0
    assert "install" in result.output
    assert "stdio" in result.output.lower() or "MCP" in result.output


def test_server_help() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["server", "--help"])
    assert result.exit_code == 0
    assert "mcp" in result.output.lower() or "stdio" in result.output.lower()


def test_mcp_install_prints_json() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["mcp", "install"])
    assert result.exit_code == 0
    assert '"mcpServers"' in result.output
    assert '"rebrief"' in result.output
    assert '"args": [' in result.output
    assert "mcp" in result.output
    assert "claude mcp add rebrief" in result.output
    assert "--write" in result.output


def test_mcp_install_write_cursor(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    existing = tmp_path / ".cursor"
    existing.mkdir()
    (existing / "mcp.json").write_text(
        '{"mcpServers": {"other": {"command": "echo"}}}\n',
        encoding="utf-8",
    )
    runner = CliRunner()
    result = runner.invoke(main, ["mcp", "install", "--client", "cursor", "--write"])
    assert result.exit_code == 0, result.output
    payload = json.loads((tmp_path / ".cursor" / "mcp.json").read_text(encoding="utf-8"))
    assert payload["mcpServers"]["other"]["command"] == "echo"
    assert payload["mcpServers"]["rebrief"] == {"command": "rebrief", "args": ["mcp"]}


def test_mcp_missing_extra(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom() -> None:
        raise ImportError("No module named 'mcp'")

    monkeypatch.setattr("rebrief.cli._import_mcp_run_stdio", boom)
    runner = CliRunner()
    result = runner.invoke(main, ["mcp"])
    assert result.exit_code == 1
    assert "rebrief[mcp]" in result.output


def test_mcp_starts_server(monkeypatch: pytest.MonkeyPatch) -> None:
    called = {"n": 0}

    def fake_run() -> None:
        called["n"] += 1

    monkeypatch.setattr("rebrief.cli._import_mcp_run_stdio", lambda: fake_run)
    runner = CliRunner()
    result = runner.invoke(main, ["mcp"])
    assert result.exit_code == 0, result.output
    assert called["n"] == 1


def test_server_alias_starts_server(monkeypatch: pytest.MonkeyPatch) -> None:
    called = {"n": 0}

    def fake_run() -> None:
        called["n"] += 1

    monkeypatch.setattr("rebrief.cli._import_mcp_run_stdio", lambda: fake_run)
    runner = CliRunner()
    result = runner.invoke(main, ["server"])
    assert result.exit_code == 0, result.output
    assert called["n"] == 1

