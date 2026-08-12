from __future__ import annotations

import json
from pathlib import Path

import pytest

from rebrief.core.confidence import Confidence
from rebrief.core.reporter import ReportGenerator
from rebrief.core.tokens import (
    CHAR_RATIO,
    ENCODING_NAME,
    FALLBACK_TOKENIZER,
    complete_token_stats,
    count_repo_tokens,
    count_tokens,
    format_compact_count,
    format_savings_footnote,
    reset_tokenizer_cache,
    savings_percentage,
)
from tests.test_reporter import make_report_data

SAMPLE_MARKDOWN = "# Hello\n\nThis is a **brief** report with `code`.\n"
SAMPLE_JSON = json.dumps(
    {"summary": {"languages_count": 1, "risks_count": 0}, "checklist": ["Start here."]},
    indent=2,
)


@pytest.fixture(autouse=True)
def _reset_tokenizer() -> None:
    reset_tokenizer_cache()
    yield
    reset_tokenizer_cache()


def test_count_tokens_markdown_matches_cl100k_base() -> None:
    tiktoken = pytest.importorskip("tiktoken")
    encoding = tiktoken.get_encoding(ENCODING_NAME)
    expected = len(encoding.encode(SAMPLE_MARKDOWN, disallowed_special=()))
    assert count_tokens(SAMPLE_MARKDOWN) == expected
    assert expected > 0


def test_count_tokens_json_payload_matches_cl100k_base() -> None:
    tiktoken = pytest.importorskip("tiktoken")
    encoding = tiktoken.get_encoding(ENCODING_NAME)
    expected = len(encoding.encode(SAMPLE_JSON, disallowed_special=()))
    assert count_tokens(SAMPLE_JSON) == expected


def test_count_tokens_falls_back_to_char_ratio(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("rebrief.core.tokens._get_encoding", lambda: None)
    assert count_tokens("") == 0
    assert count_tokens("ab") == 1
    assert count_tokens(SAMPLE_MARKDOWN) == max(1, len(SAMPLE_MARKDOWN) // CHAR_RATIO)
    assert count_tokens(SAMPLE_JSON) == max(1, len(SAMPLE_JSON) // CHAR_RATIO)


def test_savings_percentage() -> None:
    assert savings_percentage(45200, 850) == 98.12
    assert savings_percentage(0, 10) == 0.0
    assert savings_percentage(100, 100) == 0.0


def test_format_compact_count() -> None:
    assert format_compact_count(850) == "850"
    assert format_compact_count(45200) == "45.2k"
    assert format_compact_count(1_000_000) == "1M"


def test_count_repo_tokens_sums_text_and_skips_binary(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("print('hello world')\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# Demo\n\nNotes.\n", encoding="utf-8")
    (tmp_path / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)
    (tmp_path / "blob.bin").write_bytes(b"text\x00more")
    (tmp_path / "REBRIEF.md").write_text("# old report\n" * 50, encoding="utf-8")
    vendor = tmp_path / "node_modules" / "pkg"
    vendor.mkdir(parents=True)
    (vendor / "index.js").write_text("module.exports = 1;\n", encoding="utf-8")

    stats = count_repo_tokens(tmp_path)
    expected = count_tokens("print('hello world')\n") + count_tokens("# Demo\n\nNotes.\n")
    assert stats["raw_codebase_tokens"] == expected
    assert stats["brief_tokens"] == 0
    assert stats["tokenizer"] in {ENCODING_NAME, FALLBACK_TOKENIZER}


def test_count_repo_tokens_incremental_paths(tmp_path: Path) -> None:
    (tmp_path / "keep.py").write_text("keep = True\n", encoding="utf-8")
    (tmp_path / "skip.py").write_text("skip = True\n" * 20, encoding="utf-8")

    stats = count_repo_tokens(tmp_path, paths=["keep.py"])
    assert stats["raw_codebase_tokens"] == count_tokens("keep = True\n")


def test_reporter_includes_token_stats_and_footnote(tmp_path: Path) -> None:
    stack, rules, git_log, risks = make_report_data()
    raw = complete_token_stats(45200, 0, ENCODING_NAME)
    generator = ReportGenerator(
        str(tmp_path / "demo-repo"),
        stack,
        rules,
        git_log,
        risks,
        min_confidence=Confidence.MEDIUM,
        raw_token_stats=raw,
    )
    report = generator.generate()
    payload = generator.to_dict()
    stats = payload["summary"]["token_stats"]

    assert "Token Savings:" in report
    assert format_savings_footnote(stats) in report
    assert set(stats.keys()) == {
        "raw_codebase_tokens",
        "brief_tokens",
        "savings_percentage",
        "tokenizer",
    }
    assert stats["raw_codebase_tokens"] == 45200
    assert stats["brief_tokens"] == count_tokens(generator._body())
    assert stats["savings_percentage"] == savings_percentage(45200, stats["brief_tokens"])
    assert stats["tokenizer"] == ENCODING_NAME
    assert json.loads(generator.generate_json())["summary"]["token_stats"] == stats
