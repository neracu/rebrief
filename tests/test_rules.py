from pathlib import Path

from rebrief.parsers.rules import PREVIEW_LINE_COUNT, RulesParser


def test_empty_repo(tmp_path: Path) -> None:
    result = RulesParser(str(tmp_path)).parse()

    assert result == {}


def test_cursorrules_full_content(tmp_path: Path) -> None:
    content = "# Role\nBe concise.\n"
    (tmp_path / ".cursorrules").write_text(content, encoding="utf-8")

    result = RulesParser(str(tmp_path)).parse()

    assert set(result.keys()) == {".cursorrules"}
    assert result[".cursorrules"]["content"] == content
    assert result[".cursorrules"]["lines_count"] == 2


def test_readme_preview(tmp_path: Path) -> None:
    lines = [f"line {index}" for index in range(1, 16)]
    (tmp_path / "README.md").write_text("\n".join(lines), encoding="utf-8")

    result = RulesParser(str(tmp_path)).parse()

    assert result["README.md"]["lines_count"] == 15
    assert result["README.md"]["content"] == "\n".join(lines[:PREVIEW_LINE_COUNT])
    assert "line 11" not in result["README.md"]["content"]


def test_large_config_preview(tmp_path: Path) -> None:
    lines = [f"rule {index}" for index in range(1, 251)]
    (tmp_path / "CLAUDE.md").write_text("\n".join(lines), encoding="utf-8")

    result = RulesParser(str(tmp_path)).parse()

    assert result["CLAUDE.md"]["lines_count"] == 250
    assert result["CLAUDE.md"]["content"] == "\n".join(lines[:PREVIEW_LINE_COUNT])
    assert "rule 11" not in result["CLAUDE.md"]["content"]


def test_case_insensitive_match(tmp_path: Path) -> None:
    (tmp_path / "readme.md").write_text("# Demo\n", encoding="utf-8")

    result = RulesParser(str(tmp_path)).parse()

    assert "README.md" in result
    assert result["README.md"]["lines_count"] == 1


def test_missing_files_ignored(tmp_path: Path) -> None:
    (tmp_path / ".cursorrules").write_text("rules\n", encoding="utf-8")

    result = RulesParser(str(tmp_path)).parse()

    assert set(result.keys()) == {".cursorrules"}


def test_encoding_errors_ignored(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_bytes(b"valid text\xff\xfe\nmore text\n")

    result = RulesParser(str(tmp_path)).parse()

    assert "AGENTS.md" in result
    assert result["AGENTS.md"]["lines_count"] >= 1


def test_cursor_rules_mdc_files_discovered(tmp_path: Path) -> None:
    rules_dir = tmp_path / ".cursor" / "rules"
    rules_dir.mkdir(parents=True)
    foo_content = "# Python rules\nBe strict.\n"
    (rules_dir / "foo.mdc").write_text(foo_content, encoding="utf-8")
    nested_dir = rules_dir / "nested"
    nested_dir.mkdir()
    (nested_dir / "bar.mdc").write_text("# Testing\n", encoding="utf-8")
    (tmp_path / ".cursorrules").write_text("root rules\n", encoding="utf-8")

    result = RulesParser(str(tmp_path)).parse()

    assert set(result.keys()) == {
        ".cursorrules",
        ".cursor/rules/foo.mdc",
        ".cursor/rules/nested/bar.mdc",
    }
    assert result[".cursor/rules/foo.mdc"]["content"] == foo_content
    assert result[".cursor/rules/foo.mdc"]["lines_count"] == 2
    assert result[".cursor/rules/nested/bar.mdc"]["lines_count"] == 1


def test_cursor_rules_mdc_missing_dir(tmp_path: Path) -> None:
    (tmp_path / ".cursorrules").write_text("rules\n", encoding="utf-8")

    result = RulesParser(str(tmp_path)).parse()

    assert set(result.keys()) == {".cursorrules"}
