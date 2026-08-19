from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from rebrief.cli import main
from rebrief.core.config import (
    CliOverrides,
    ConfigError,
    load_config,
    resolve_effective_settings,
)
from rebrief.core.confidence import Confidence
from rebrief.core.ignore import IgnoreMatcher
from rebrief.core.scan import run_scan
from rebrief.parsers.git_log import GitLogParser
from rebrief.parsers.risks import RisksParser


def test_discover_rebrief_toml(tmp_path: Path) -> None:
    (tmp_path / "rebrief.toml").write_text(
        '[general]\nformat = "json"\n',
        encoding="utf-8",
    )

    config = load_config(tmp_path)

    assert config.general.format == "json"
    assert config.source_paths == (tmp_path / "rebrief.toml",)


def test_dotfile_overrides_base(tmp_path: Path) -> None:
    (tmp_path / "rebrief.toml").write_text(
        '[general]\nformat = "markdown"\nmin_confidence = "low"\n',
        encoding="utf-8",
    )
    (tmp_path / ".rebrief.toml").write_text(
        '[general]\nmin_confidence = "high"\n',
        encoding="utf-8",
    )

    config = load_config(tmp_path)

    assert config.general.format == "markdown"
    assert config.general.min_confidence == "high"
    assert len(config.source_paths) == 2


def test_explicit_config_path(tmp_path: Path) -> None:
    (tmp_path / "rebrief.toml").write_text(
        '[general]\nformat = "markdown"\n',
        encoding="utf-8",
    )
    custom = tmp_path / "custom.toml"
    custom.write_text('[general]\nformat = "xml"\n', encoding="utf-8")

    config = load_config(tmp_path, custom)

    assert config.general.format == "xml"
    assert config.source_paths == (custom,)


def test_invalid_schema_raises(tmp_path: Path) -> None:
    (tmp_path / "rebrief.toml").write_text(
        "[thresholds]\nmax_hotspots = 0\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="max_hotspots must be >= 1"):
        load_config(tmp_path)


def test_unknown_key_raises(tmp_path: Path) -> None:
    (tmp_path / "rebrief.toml").write_text(
        "[general]\nunknown = true\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="unknown key"):
        load_config(tmp_path)


def test_cli_overrides_config(tmp_path: Path) -> None:
    (tmp_path / "rebrief.toml").write_text(
        '[general]\nformat = "markdown"\n',
        encoding="utf-8",
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("print('ok')\n", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["scan", str(tmp_path), "-f", "json", "-o", "-", "-y"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert "summary" in payload


def test_ignore_patterns_from_config(tmp_path: Path) -> None:
    (tmp_path / "rebrief.toml").write_text(
        '[ignore]\npaths = ["vendor/**"]\nfiles = ["*.pb.go"]\n',
        encoding="utf-8",
    )
    config = load_config(tmp_path)
    patterns = config.ignore.paths + config.ignore.files

    matcher = IgnoreMatcher(tmp_path, extra_patterns=patterns)

    assert matcher.is_ignored("vendor/lib/module.js", is_dir=False) is True
    assert matcher.is_ignored("generated.pb.go", is_dir=False) is True
    assert matcher.is_ignored("src/app.py", is_dir=False) is False


def test_ignore_patterns_skip_secrets_in_config(tmp_path: Path) -> None:
    (tmp_path / "rebrief.toml").write_text(
        '[ignore]\npaths = ["secrets/"]\n',
        encoding="utf-8",
    )
    config = load_config(tmp_path)
    secret_dir = tmp_path / "secrets"
    secret_dir.mkdir()
    (secret_dir / "keys.py").write_text(
        'api_key = "aB3xQ9mK7pL2wZ8vN4tR"\n',
        encoding="utf-8",
    )

    result = RisksParser(
        str(tmp_path),
        extra_ignore_patterns=config.ignore.paths,
    ).parse()

    assert result["secrets"] == []


def test_custom_secret_pattern(tmp_path: Path) -> None:
    (tmp_path / "rebrief.toml").write_text(
        """
[secrets]
custom_patterns = [
  { name = "Internal Auth Token", regex = "ACME_AUTH_[A-Za-z0-9]{32}", confidence = "HIGH" }
]
""".strip()
        + "\n",
        encoding="utf-8",
    )
    config = load_config(tmp_path)
    (tmp_path / "config.py").write_text(
        'auth_token = "ACME_AUTH_AbCdEfGhIjKlMnOpQrStUvWxYz123456"\n',
        encoding="utf-8",
    )
    patterns = tuple(
        (item.regex, item.confidence) for item in config.secrets.custom_patterns
    )

    result = RisksParser(str(tmp_path), custom_patterns=patterns).parse()

    assert len(result["secrets"]) == 1
    assert result["secrets"][0]["confidence"] == "HIGH"


def test_entropy_cutoff_from_config(tmp_path: Path) -> None:
    config_text = """
[thresholds]
entropy_cutoff = 4.5
""".strip()
    (tmp_path / "rebrief.toml").write_text(config_text + "\n", encoding="utf-8")
    config = load_config(tmp_path)
    (tmp_path / "settings.py").write_text(
        'api_key = "aB3xQ9mK7pL2wZ8vN4tR"\n',
        encoding="utf-8",
    )

    default_result = RisksParser(str(tmp_path)).parse()
    strict_result = RisksParser(
        str(tmp_path),
        entropy_cutoff=config.thresholds.entropy_cutoff,
    ).parse()

    assert len(default_result["secrets"]) == 1
    assert strict_result["secrets"] == []


@patch("rebrief.parsers.git_log.subprocess.run")
def test_max_hotspots_from_config(mock_run: MagicMock, tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    (tmp_path / "rebrief.toml").write_text(
        "[thresholds]\nmax_hotspots = 3\n",
        encoding="utf-8",
    )
    config = load_config(tmp_path)

    def side_effect(cmd: list[str], **kwargs: object) -> MagicMock:
        result = MagicMock()
        result.returncode = 0
        if "--name-only" in cmd:
            result.stdout = "\n".join(f"file{i}.py" for i in range(10))
        else:
            result.stdout = ""
        return result

    mock_run.side_effect = side_effect

    limited = GitLogParser(
        str(tmp_path),
        max_churn_files=config.thresholds.max_hotspots,
    ).parse()

    assert len(limited["top_modified_files"]) == 3


def test_resolve_effective_settings_precedence(tmp_path: Path) -> None:
    (tmp_path / "rebrief.toml").write_text(
        """
[general]
format = "xml"
min_confidence = "low"

[vulnerabilities]
skip_osv = true
""".strip()
        + "\n",
        encoding="utf-8",
    )
    config = load_config(tmp_path)
    effective = resolve_effective_settings(
        config,
        CliOverrides(format="json", skip_vulnerability_check=False),
    )

    assert effective.format == "json"
    assert effective.min_confidence == "low"
    assert effective.skip_vulnerability_check is False


def test_run_scan_honors_config_thresholds(tmp_path: Path) -> None:
    (tmp_path / "rebrief.toml").write_text(
        """
[thresholds]
max_hotspots = 2
entropy_cutoff = 4.5
""".strip()
        + "\n",
        encoding="utf-8",
    )
    config = load_config(tmp_path)
    effective = resolve_effective_settings(config, CliOverrides())
    (tmp_path / "settings.py").write_text(
        'api_key = "aB3xQ9mK7pL2wZ8vN4tR"\n',
        encoding="utf-8",
    )

    generator = run_scan(
        tmp_path,
        Confidence.MEDIUM,
        max_churn_files=effective.max_churn_files,
        entropy_cutoff=effective.entropy_cutoff,
    )
    payload = generator.to_dict()

    assert len(payload["timeline"]["hotspots"]) <= effective.max_churn_files
    critical = payload["risk_map"]["critical"]
    assert not any("Hard-coded secret" in item["message"] for item in critical)


def test_scan_help_lists_config_flag() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["scan", "--help"])

    assert result.exit_code == 0
    assert "--config" in result.output
