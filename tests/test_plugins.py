from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from click.testing import CliRunner

from rebrief.cli import main
from rebrief.core.confidence import Confidence
from rebrief.core.scan import run_scan
from rebrief.plugins.loader import resolve_plugins, run_risk_plugins
from rebrief.plugins.context import build_scan_context
from rebrief.parsers.git_log import GitLogResult
from rebrief.parsers.ownership import OwnershipResult
from rebrief.parsers.stack import StackResult

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "plugins"


def _empty_stack() -> StackResult:
    return {
        "languages": [],
        "manifests": [],
        "frameworks": [],
        "dependencies": [],
        "packages": [],
        "is_empty": False,
        "manifest_warnings": [],
    }


def _empty_git_log() -> GitLogResult:
    return {"commits": [], "top_modified_files": [], "status_message": None}


def _empty_ownership() -> OwnershipResult:
    return {"modules": {}, "skipped": False, "skip_reason": None}


def _seed_repo(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "app.py").write_text("print('ok')\n", encoding="utf-8")


def test_local_plugin_loaded(tmp_path: Path) -> None:
    _seed_repo(tmp_path)
    plugins_dir = tmp_path / ".rebrief" / "plugins"
    plugins_dir.mkdir(parents=True)
    shutil.copy(FIXTURES_DIR / "sample_detector.py", plugins_dir / "sample_detector.py")

    generator = run_scan(tmp_path, Confidence.LOW, enable_plugins=True)
    payload = generator.to_dict()

    warning_messages = [
        item["message"] for item in payload["risk_map"]["warning"]
    ]
    assert "Sample plugin detected a custom risk." in warning_messages


def test_failing_plugin_is_isolated(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _seed_repo(tmp_path)
    plugins_dir = tmp_path / ".rebrief" / "plugins"
    plugins_dir.mkdir(parents=True)
    shutil.copy(FIXTURES_DIR / "failing_detector.py", plugins_dir / "failing_detector.py")

    generator = run_scan(tmp_path, Confidence.LOW, enable_plugins=True)
    payload = generator.to_dict()

    captured = capsys.readouterr()
    assert "Plugin 'failing-detector' failed during execution" in captured.err
    assert payload["summary"]["risks_count"] >= 0


def test_no_plugins_skips_external(tmp_path: Path) -> None:
    _seed_repo(tmp_path)
    plugins_dir = tmp_path / ".rebrief" / "plugins"
    plugins_dir.mkdir(parents=True)
    shutil.copy(FIXTURES_DIR / "sample_detector.py", plugins_dir / "sample_detector.py")

    generator = run_scan(tmp_path, Confidence.LOW, enable_plugins=False)
    payload = generator.to_dict()
    warning_messages = [
        item["message"] for item in payload["risk_map"]["warning"]
    ]
    assert "Sample plugin detected a custom risk." not in warning_messages


def test_disabled_builtin_plugin(tmp_path: Path) -> None:
    (tmp_path / "config.py").write_text(
        'api_key = "aB3xQ9mK7pL2wZ8vN4tR"\n',
        encoding="utf-8",
    )

    with_secrets = run_scan(tmp_path, Confidence.LOW)
    without_secrets = run_scan(
        tmp_path,
        Confidence.LOW,
        disabled_plugins=("secrets",),
    )

    with_critical = with_secrets.to_dict()["risk_map"]["critical"]
    without_critical = without_secrets.to_dict()["risk_map"]["critical"]
    assert any("Hard-coded secret" in item["message"] for item in with_critical)
    assert not any("Hard-coded secret" in item["message"] for item in without_critical)


def test_list_plugins_cli(tmp_path: Path) -> None:
    _seed_repo(tmp_path)
    plugins_dir = tmp_path / ".rebrief" / "plugins"
    plugins_dir.mkdir(parents=True)
    shutil.copy(FIXTURES_DIR / "sample_detector.py", plugins_dir / "sample_detector.py")

    runner = CliRunner()
    result = runner.invoke(main, ["scan", "--list-plugins", str(tmp_path)])

    assert result.exit_code == 0
    assert "secrets" in result.output
    assert "sample-detector" in result.output


def test_builtin_plugins_always_loaded(tmp_path: Path) -> None:
    _seed_repo(tmp_path)
    plugins = resolve_plugins(tmp_path, enable_external=False)
    names = {plugin.name for plugin in plugins}
    assert names == {"secrets", "markers", "missing-tests", "dependency-conflicts"}


def test_run_risk_plugins_returns_items(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("# TODO fix\n", encoding="utf-8")
    context = build_scan_context(
        tmp_path,
        stack=_empty_stack(),
        git_log=_empty_git_log(),
        ownership=_empty_ownership(),
        entropy_cutoff=3.5,
    )
    plugins = resolve_plugins(tmp_path, enable_external=False)
    items = run_risk_plugins(plugins, context)
    assert any("TODO" in item["message"] for item in items)
