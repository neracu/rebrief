from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from rebrief.cli import main
from rebrief.parsers.freshness import (
    FreshnessParser,
    compute_freshness_score,
    empty_doc_drift_report,
    freshness_label,
)
from rebrief.parsers.stack import StackParser

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "doc_drift"
MISMATCHED_DIR = FIXTURES_DIR / "mismatched"
ALIGNED_DIR = FIXTURES_DIR / "aligned"


def _parse_stack(repo: Path):
    return StackParser(str(repo)).parse()


def test_empty_repo_returns_fresh_score(tmp_path: Path) -> None:
    result = FreshnessParser(str(tmp_path), _parse_stack(tmp_path)).parse()
    assert result == empty_doc_drift_report()


def test_mismatched_fixture_detects_stack_path_and_env_drift() -> None:
    stack = _parse_stack(MISMATCHED_DIR)
    result = FreshnessParser(str(MISMATCHED_DIR), stack).parse()

    assert result["freshness_score"] < 90
    assert result["freshness_label"] in {"Needs Review", "Stale"}
    assert "README.md" in result["scanned_files"]
    assert ".cursorrules" in result["scanned_files"]

    kinds = {item["kind"] for item in result["items"]}
    assert "stack" in kinds
    assert "path" in kinds
    assert "env" in kinds

    stack_messages = [item["message"] for item in result["items"] if item["kind"] == "stack"]
    assert any("Vue" in message and "React" in message for message in stack_messages)

    path_messages = [item["message"] for item in result["items"] if item["kind"] == "path"]
    assert any("src/old_components" in message for message in path_messages)

    env_messages = [item["message"] for item in result["items"] if item["kind"] == "env"]
    assert any("API_KEY" in message for message in env_messages)
    assert any(item["severity"] == "warning" for item in result["items"])


def test_aligned_fixture_has_high_freshness_score() -> None:
    stack = _parse_stack(ALIGNED_DIR)
    result = FreshnessParser(str(ALIGNED_DIR), stack).parse()

    assert result["freshness_score"] >= 70
    stack_items = [item for item in result["items"] if item["kind"] == "stack"]
    assert stack_items == []


def test_freshness_score_formula() -> None:
    components = {
        "path_ratio": 0.5,
        "stack_ratio": 0.0,
        "env_ratio": 1.0,
        "recency_ratio": 1.0,
    }
    assert compute_freshness_score(components) == 48
    assert freshness_label(48) == "Stale"
    assert freshness_label(90) == "Fresh"
    assert freshness_label(75) == "Needs Review"


def test_path_only_drift(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "See `src/missing/feature/` for details.\n",
        encoding="utf-8",
    )
    stack = _parse_stack(tmp_path)
    result = FreshnessParser(str(tmp_path), stack).parse()

    path_items = [item for item in result["items"] if item["kind"] == "path"]
    assert len(path_items) == 1
    assert path_items[0]["severity"] == "warning"
    assert "missing" in path_items[0]["message"]


def test_env_extra_in_docs_is_info(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "Set `SECRET_TOKEN` via process.env.SECRET_TOKEN.\n",
        encoding="utf-8",
    )
    (tmp_path / ".env.example").write_text("API_KEY=value\n", encoding="utf-8")
    stack = _parse_stack(tmp_path)
    result = FreshnessParser(str(tmp_path), stack).parse()

    info_items = [item for item in result["items"] if item["severity"] == "info"]
    assert any("SECRET_TOKEN" in item["message"] for item in info_items)


def test_docs_directory_is_scanned(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "guide.md").write_text(
        "Built with React and Vite.\n",
        encoding="utf-8",
    )
    (tmp_path / "package.json").write_text(
        '{"dependencies":{"react":"^18.0.0"},"devDependencies":{"vite":"^5.0.0"}}',
        encoding="utf-8",
    )
    stack = _parse_stack(tmp_path)
    result = FreshnessParser(str(tmp_path), stack).parse()

    assert "docs/guide.md" in result["scanned_files"]
    assert result["freshness_score"] >= 70


def test_cli_scan_json_includes_doc_drift() -> None:
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["scan", str(MISMATCHED_DIR), "-f", "json", "-o", "-"],
    )
    assert result.exit_code == 0
    json_start = result.output.find("{")
    payload = json.loads(result.output[json_start:])
    doc_drift = payload["summary"]["doc_drift"]
    assert "freshness_score" in doc_drift
    assert doc_drift["items"]


def test_backtick_cli_flags_are_not_paths(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "Use `--no-blame`, `freshness_score`, and `rebrief scan`.\n",
        encoding="utf-8",
    )
    result = FreshnessParser(str(tmp_path), _parse_stack(tmp_path)).parse()
    assert [item for item in result["items"] if item["kind"] == "path"] == []


def test_dotfile_path_preserves_leading_dot(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "See `.cursorrules` for rules.\n",
        encoding="utf-8",
    )
    result = FreshnessParser(str(tmp_path), _parse_stack(tmp_path)).parse()
    path_items = [item for item in result["items"] if item["kind"] == "path"]
    assert len(path_items) == 1
    assert "`.cursorrules`" in path_items[0]["message"]


def test_catalog_readme_does_not_flag_stack(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "Supports Vue, React, and Angular frontends.\n",
        encoding="utf-8",
    )
    (tmp_path / "package.json").write_text(
        '{"dependencies":{"react":"^18.0.0"}}',
        encoding="utf-8",
    )
    result = FreshnessParser(str(tmp_path), _parse_stack(tmp_path)).parse()
    assert [item for item in result["items"] if item["kind"] == "stack"] == []


def test_react_and_next_not_conflicting(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "Built with React and Next.js.\n",
        encoding="utf-8",
    )
    (tmp_path / "package.json").write_text(
        '{"dependencies":{"react":"^18.0.0","next":"^14.0.0"}}',
        encoding="utf-8",
    )
    result = FreshnessParser(str(tmp_path), _parse_stack(tmp_path)).parse()
    assert [item for item in result["items"] if item["kind"] == "stack"] == []


def test_code_constants_are_not_env_vars(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "Edit `MANIFEST_FILES` and `FRAMEWORK_SIGNATURES` in rules.py.\n",
        encoding="utf-8",
    )
    (tmp_path / ".env.example").write_text("API_KEY=value\n", encoding="utf-8")
    result = FreshnessParser(str(tmp_path), _parse_stack(tmp_path)).parse()
    env_items = [item for item in result["items"] if item["kind"] == "env"]
    assert not any("MANIFEST_FILES" in item["message"] for item in env_items)
    assert not any("FRAMEWORK_SIGNATURES" in item["message"] for item in env_items)


def test_nested_package_json_counts_as_valid(tmp_path: Path) -> None:
    web = tmp_path / "web"
    web.mkdir()
    (web / "package.json").write_text('{"name":"web"}', encoding="utf-8")
    (tmp_path / "README.md").write_text(
        "See `package.json` for dependencies.\n",
        encoding="utf-8",
    )
    result = FreshnessParser(str(tmp_path), _parse_stack(tmp_path)).parse()
    assert [item for item in result["items"] if item["kind"] == "path"] == []


def test_generated_rebrief_md_is_not_flagged(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "Output is written to `REBRIEF.md`.\n",
        encoding="utf-8",
    )
    result = FreshnessParser(str(tmp_path), _parse_stack(tmp_path)).parse()
    assert [item for item in result["items"] if item["kind"] == "path"] == []


def test_json_property_paths_are_not_flagged(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "See `summary.token_stats` and `summary.files_scanned` in JSON.\n",
        encoding="utf-8",
    )
    result = FreshnessParser(str(tmp_path), _parse_stack(tmp_path)).parse()
    assert [item for item in result["items"] if item["kind"] == "path"] == []


def test_manifest_catalog_skips_supported_format_list(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "Supports `go.mod`, `Cargo.toml`, `pom.xml`, and `composer.json`.\n",
        encoding="utf-8",
    )
    result = FreshnessParser(str(tmp_path), _parse_stack(tmp_path)).parse()
    assert [item for item in result["items"] if item["kind"] == "path"] == []


def test_paths_inside_code_blocks_are_ignored(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "## Example\n```markdown\nSee `apps/backend` and `src/app.py`.\n```\n",
        encoding="utf-8",
    )
    result = FreshnessParser(str(tmp_path), _parse_stack(tmp_path)).parse()
    assert [item for item in result["items"] if item["kind"] == "path"] == []
