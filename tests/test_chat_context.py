from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from rebrief.chat.context import format_system_prompt, load_chat_context, load_report_file
from rebrief.chat.credentials import ChatError
from rebrief.core.confidence import Confidence


def test_system_prompt_wraps_rebrief_body() -> None:
    prompt = format_system_prompt("# REBRIEF REPORT: demo\n\nPython stack.")
    assert prompt.startswith("You are Rebrief Assistant, an expert codebase analyst.")
    assert "--- BEGIN REBRIEF CONTEXT ---" in prompt
    assert "# REBRIEF REPORT: demo" in prompt
    assert "Python stack." in prompt
    assert "--- END REBRIEF CONTEXT ---" in prompt
    assert "strictly based on this architectural context" in prompt


def test_load_markdown_file(tmp_path: Path) -> None:
    report = tmp_path / "REBRIEF.md"
    report.write_text("# REBRIEF REPORT: demo\n\nHotspots.\n", encoding="utf-8")
    context = load_report_file(report)
    assert "Hotspots." in context.content
    assert "BEGIN REBRIEF CONTEXT" in context.system_prompt
    assert "Hotspots." in context.system_prompt
    assert context.source == str(report.resolve())
    assert context.token_count > 0


def test_load_json_file_pretty_prints(tmp_path: Path) -> None:
    report = tmp_path / "REBRIEF.json"
    report.write_text(json.dumps({"summary": {"risks_count": 2}}), encoding="utf-8")
    context = load_report_file(report)
    payload = json.loads(context.content)
    assert payload["summary"]["risks_count"] == 2
    assert '"risks_count": 2' in context.system_prompt


def test_load_rejects_html(tmp_path: Path) -> None:
    report = tmp_path / "REBRIEF.html"
    report.write_text("<html></html>", encoding="utf-8")
    with pytest.raises(ChatError, match="REBRIEF.md or REBRIEF.json"):
        load_report_file(report)


def test_prefers_markdown_over_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "REBRIEF.md").write_text("# from markdown\n", encoding="utf-8")
    (tmp_path / "REBRIEF.json").write_text("{}", encoding="utf-8")
    context = load_chat_context(".")
    assert "# from markdown" in context.content


def test_loads_existing_report_before_scan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "REBRIEF.md").write_text("# cached brief\n", encoding="utf-8")

    def boom(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("scan should not run")

    monkeypatch.setattr("rebrief.chat.context.run_scan", boom)
    context = load_chat_context(".")
    assert "# cached brief" in context.content


def test_live_scan_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    generator = MagicMock()
    generator.generate.return_value = "# REBRIEF REPORT: live\n"
    with patch("rebrief.chat.context.run_scan", return_value=generator) as mock_scan:
        context = load_chat_context(str(tmp_path))
    mock_scan.assert_called_once()
    assert mock_scan.call_args.args[1] == Confidence.MEDIUM
    assert context.source == "live scan"
    assert "# REBRIEF REPORT: live" in context.system_prompt


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(ChatError, match="Report not found"):
        load_report_file(tmp_path / "missing.md")
