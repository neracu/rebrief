from pathlib import Path

import pytest

from rebrief.core.ignore import (
    DEFAULT_REBRIEFIGNORE_CONTENT,
    IgnoreMatcher,
    REBRIEFIGNORE_FILENAME,
    ensure_rebriefignore,
    parse_ignore_lines,
)


def test_default_dirs_always_ignored(tmp_path: Path) -> None:
    matcher = IgnoreMatcher(tmp_path)

    assert matcher.is_ignored("node_modules/lib/index.js", is_dir=False) is True
    assert matcher.is_ignored(".next/server/page.js", is_dir=False) is True
    assert matcher.is_ignored("__pycache__/module.pyc", is_dir=False) is True
    assert matcher.should_prune_dir("node_modules", "") is True
    assert matcher.should_prune_dir(".next", "frontend") is True


def test_rebriefignore_custom_pattern(tmp_path: Path) -> None:
    (tmp_path / REBRIEFIGNORE_FILENAME).write_text("vendor/\n", encoding="utf-8")
    matcher = IgnoreMatcher(tmp_path)

    assert matcher.is_ignored("vendor/lib.js", is_dir=False) is True
    assert matcher.should_prune_dir("vendor", "static") is True
    assert matcher.is_ignored("src/app.py", is_dir=False) is False


def test_parses_comments_and_blank_lines() -> None:
    text = """
# Dependencies
node_modules/

# Build
dist/

"""

    assert parse_ignore_lines(text) == ["node_modules/", "dist/"]


def test_directory_only_pattern(tmp_path: Path) -> None:
    (tmp_path / REBRIEFIGNORE_FILENAME).write_text("artifacts/\n", encoding="utf-8")
    matcher = IgnoreMatcher(tmp_path)

    assert matcher.is_ignored("artifacts", is_dir=True) is True
    assert matcher.is_ignored("artifacts", is_dir=False) is False
    assert matcher.is_ignored("artifacts/output.js", is_dir=False) is True


def test_ensure_rebriefignore_creates_file(tmp_path: Path) -> None:
    created = ensure_rebriefignore(tmp_path)

    assert created is True
    content = (tmp_path / REBRIEFIGNORE_FILENAME).read_text(encoding="utf-8")
    assert content == DEFAULT_REBRIEFIGNORE_CONTENT
    assert "node_modules/" in content
    assert "# Dependencies and package managers" in content


def test_ensure_rebriefignore_idempotent(tmp_path: Path) -> None:
    ignore_path = tmp_path / REBRIEFIGNORE_FILENAME
    ignore_path.write_text("custom/\n", encoding="utf-8")

    created = ensure_rebriefignore(tmp_path)

    assert created is False
    assert ignore_path.read_text(encoding="utf-8") == "custom/\n"


def test_ensure_rebriefignore_write_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_write(*_args: object, **_kwargs: object) -> None:
        raise OSError("permission denied")

    monkeypatch.setattr(Path, "write_text", fail_write)

    with pytest.raises(OSError, match="Failed to create"):
        ensure_rebriefignore(tmp_path)
