from __future__ import annotations

from io import StringIO
from pathlib import Path

import pytest
from rich.console import Console

from rebrief.core.confidence import Confidence
from rebrief.core.reporter import ReportGenerator, ReportPayload
from rebrief.ui import (
    BANNER_ART,
    BANNER_ART_ASCII,
    CHURN_BAR_WIDTH,
    SUBTITLE,
    ScanSettings,
    ScanUI,
    churn_bar,
    confidence_label,
    resolve_plain,
)
from tests.test_reporter import make_report_data


def _fancy_ui() -> ScanUI:
    console = Console(record=True, force_terminal=True, highlight=False, width=80)
    return ScanUI(console, plain=False)


def _plain_ui() -> ScanUI:
    console = Console(record=True, no_color=True, highlight=False, width=80, emoji=False)
    return ScanUI(console, plain=True)


def _settings(**overrides: object) -> ScanSettings:
    values: dict[str, object] = {
        "target": ".",
        "format": "markdown",
        "output": "REBRIEF.md",
        "min_confidence": "medium",
        "diff_ref": None,
        "inject_badge": False,
        "output_custom": False,
    }
    values.update(overrides)
    return ScanSettings(**values)  # type: ignore[arg-type]


class _AsciiStream(StringIO):
    encoding = "ascii"


class _TTY:
    def isatty(self) -> bool:
        return True


def _payload(tmp_path: Path, min_confidence: Confidence = Confidence.LOW) -> ReportPayload:
    stack, rules, git_log, risks = make_report_data()
    generator = ReportGenerator(
        str(tmp_path / "demo-repo"),
        stack,
        rules,
        git_log,
        risks,
        min_confidence=min_confidence,
    )
    return generator.to_dict()


def test_confidence_label() -> None:
    assert confidence_label("HIGH") == "[HIGH]"
    assert confidence_label("MEDIUM") == "[MEDIUM]"
    assert confidence_label("LOW") == "[NEEDS_VERIFICATION]"


def test_churn_bar_plain_scales_to_max() -> None:
    full = churn_bar(8, 8, plain=True)
    half = churn_bar(4, 8, plain=True)
    empty = churn_bar(0, 8, plain=True)
    assert str(full) == "#" * CHURN_BAR_WIDTH
    assert str(half).count("#") == CHURN_BAR_WIDTH // 2
    assert str(empty) == "-" * CHURN_BAR_WIDTH
    assert "█" not in str(full)


def test_churn_bar_fancy_uses_blocks() -> None:
    bar = churn_bar(8, 8, plain=False)
    assert "█" in str(bar)
    assert bar.style == "red"


def test_resolve_plain_flag_and_no_color(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    assert resolve_plain(True) is True
    monkeypatch.setenv("NO_COLOR", "1")
    assert resolve_plain(False) is True


def test_banner_fancy_includes_art_and_subtitle() -> None:
    ui = _fancy_ui()
    ui.print_banner()
    text = ui.console.export_text()
    assert BANNER_ART.split("\n")[0] in text
    assert SUBTITLE in text


def test_banner_plain_skips_art_and_emoji() -> None:
    ui = _plain_ui()
    ui.print_banner()
    text = ui.console.export_text()
    assert BANNER_ART.split("\n")[0] not in text
    assert BANNER_ART_ASCII.split("\n")[0] not in text
    assert "rebrief" in text.lower()
    assert SUBTITLE in text
    assert "⚡" not in text


def test_banner_ascii_fallback_when_encoding_lacks_blocks() -> None:
    stream = _AsciiStream()
    console = Console(file=stream, force_terminal=True, highlight=False, width=80)
    ui = ScanUI(console, plain=False)
    assert ui.banner_art() == BANNER_ART_ASCII


def test_should_prompt_settings_gates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("NO_COLOR", raising=False)
    fancy = _fancy_ui()
    assert fancy.should_prompt_settings(stdin=_TTY()) is True
    assert fancy.should_prompt_settings(yes=True, stdin=_TTY()) is False
    assert _plain_ui().should_prompt_settings(stdin=_TTY()) is False
    monkeypatch.setenv("CI", "true")
    assert fancy.should_prompt_settings(stdin=_TTY()) is False


def test_print_settings_panel_lists_fields() -> None:
    ui = _fancy_ui()
    ui.print_settings_panel(_settings(diff_ref="HEAD~1"))
    text = ui.console.export_text()
    assert "Target" in text
    assert "Format" in text
    assert "Output" in text
    assert "Min confidence" in text
    assert "Diff" in text
    assert "Inject badge" in text
    assert "Start scan" in text
    assert "Quit" in text
    assert "HEAD~1" in text


def test_prompt_settings_start_returns_defaults() -> None:
    ui = _fancy_ui()
    settings = _settings()
    result = ui.prompt_settings(settings, input_func=lambda _: "s")
    assert result is settings
    assert result.format == "markdown"
    assert result.output == "REBRIEF.md"


def test_prompt_settings_quit_returns_none() -> None:
    ui = _fancy_ui()
    result = ui.prompt_settings(_settings(), input_func=lambda _: "q")
    assert result is None


def test_prompt_settings_format_updates_default_output() -> None:
    ui = _fancy_ui()
    answers = iter(["2", "json", "s"])
    result = ui.prompt_settings(_settings(), input_func=lambda _: next(answers))
    assert result is not None
    assert result.format == "json"
    assert result.output == "REBRIEF.json"


def test_settings_region_replace_uses_cursor_restore() -> None:
    from io import StringIO

    from rebrief.ui import _CURSOR_RESTORE, _CURSOR_SAVE, _ERASE_DOWN

    stream = StringIO()
    console = Console(file=stream, force_terminal=True, highlight=False, width=80)
    ui = ScanUI(console, plain=False)
    ui._anchor_settings_region()
    ui._replace_settings_region()
    written = stream.getvalue()
    assert _CURSOR_SAVE in written
    assert _CURSOR_RESTORE in written
    assert _ERASE_DOWN in written


def test_print_results_sections_and_completion(tmp_path: Path) -> None:
    ui = _fancy_ui()
    payload = _payload(tmp_path)
    ui.print_results(payload, output_path=tmp_path / "REBRIEF.md")
    text = ui.console.export_text()

    assert "Tech Stack" in text
    assert "Python" in text
    assert "Django" in text
    assert "pyproject.toml" in text
    assert "Hotspots" in text
    assert "src/app.py" in text
    assert "CRITICAL" in text
    assert "WARNING" in text
    assert "INFO" in text
    assert "[MEDIUM]" in text
    assert "[NEEDS_VERIFICATION]" in text
    assert "Token Savings" in text
    assert "saved to REBRIEF.md" in text
    assert "tokens" in text


def test_print_results_plain_has_ascii_churn(tmp_path: Path) -> None:
    ui = _plain_ui()
    payload = _payload(tmp_path)
    ui.print_results(payload, output_path=Path("REBRIEF.md"))
    text = ui.console.export_text()
    assert "#" in text
    assert "█" not in text
    assert "saved to REBRIEF.md" in text
    assert "\x1b[" not in ui.console.export_text()


def test_print_completion_stdout() -> None:
    ui = _plain_ui()
    ui.print_completion(output_path=None, brief_tokens=850)
    assert "saved to stdout (850 tokens)" in ui.console.export_text()
