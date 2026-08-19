from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rebrief.core.confidence import Confidence, parse_confidence, parse_min_confidence
from rebrief.parsers.git_log import MAX_CHURN_FILES
from rebrief.parsers.risks import ENTROPY_THRESHOLD

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # type: ignore[no-redef]

REBRIEF_CONFIG_FILENAME = "rebrief.toml"
DOT_REBRIEF_CONFIG_FILENAME = ".rebrief.toml"

_VALID_FORMATS = frozenset({"markdown", "json", "xml", "html"})
_VALID_MIN_CONFIDENCE = frozenset({"high", "medium", "low"})
_KNOWN_TOP_LEVEL_KEYS = frozenset({
    "general",
    "ignore",
    "thresholds",
    "secrets",
    "vulnerabilities",
    "plugins",
})
_GENERAL_KEYS = frozenset({"format", "min_confidence", "output"})
_IGNORE_KEYS = frozenset({"paths", "files"})
_THRESHOLDS_KEYS = frozenset({"max_hotspots", "entropy_cutoff"})
_SECRETS_KEYS = frozenset({"custom_patterns"})
_VULNERABILITIES_KEYS = frozenset({"skip_osv"})
_PLUGINS_KEYS = frozenset({"disabled"})
_SECRET_PATTERN_KEYS = frozenset({"name", "regex", "confidence"})


class ConfigError(ValueError):
    """Raised when a rebrief.toml file is invalid or fails schema validation."""


@dataclass(frozen=True)
class GeneralConfig:
    format: str = "markdown"
    min_confidence: str = "medium"
    output: str | None = None


@dataclass(frozen=True)
class IgnoreConfig:
    paths: tuple[str, ...] = ()
    files: tuple[str, ...] = ()


@dataclass(frozen=True)
class ThresholdsConfig:
    max_hotspots: int = MAX_CHURN_FILES
    entropy_cutoff: float = ENTROPY_THRESHOLD


@dataclass(frozen=True)
class SecretPatternConfig:
    name: str
    regex: re.Pattern[str]
    confidence: Confidence


@dataclass(frozen=True)
class SecretsConfig:
    custom_patterns: tuple[SecretPatternConfig, ...] = ()


@dataclass(frozen=True)
class VulnerabilitiesConfig:
    skip_osv: bool = False


@dataclass(frozen=True)
class PluginsConfig:
    disabled: tuple[str, ...] = ()


@dataclass(frozen=True)
class RebriefConfig:
    general: GeneralConfig = field(default_factory=GeneralConfig)
    ignore: IgnoreConfig = field(default_factory=IgnoreConfig)
    thresholds: ThresholdsConfig = field(default_factory=ThresholdsConfig)
    secrets: SecretsConfig = field(default_factory=SecretsConfig)
    vulnerabilities: VulnerabilitiesConfig = field(default_factory=VulnerabilitiesConfig)
    plugins: PluginsConfig = field(default_factory=PluginsConfig)
    source_paths: tuple[Path, ...] = ()


@dataclass(frozen=True)
class EffectiveScanSettings:
    format: str
    min_confidence: str
    output: str | None
    skip_vulnerability_check: bool
    max_churn_files: int
    extra_ignore_patterns: tuple[str, ...]
    entropy_cutoff: float
    custom_secret_patterns: tuple[SecretPatternConfig, ...]
    disabled_plugins: tuple[str, ...]


@dataclass(frozen=True)
class CliOverrides:
    format: str | None = None
    min_confidence: str | None = None
    output: str | None = None
    skip_vulnerability_check: bool | None = None


def _deep_merge_dicts(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = dict(base)
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge_dicts(merged[key], value)
        else:
            merged[key] = value
    return merged


def _read_toml(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"Failed to read config file {path}: {exc}") from exc
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"Invalid TOML in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"Config file {path} must contain a TOML table at the root")
    return data


def _validate_unknown_keys(section: str, data: dict[str, Any], allowed: frozenset[str]) -> None:
    unknown = set(data) - allowed
    if unknown:
        joined = ", ".join(sorted(unknown))
        raise ConfigError(f"{section}: unknown key(s): {joined}")


def _require_str(section: str, key: str, value: object) -> str:
    if not isinstance(value, str):
        raise ConfigError(f"{section}.{key} must be a string, got {type(value).__name__}")
    return value


def _require_bool(section: str, key: str, value: object) -> bool:
    if not isinstance(value, bool):
        raise ConfigError(f"{section}.{key} must be a boolean, got {type(value).__name__}")
    return value


def _require_int(section: str, key: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{section}.{key} must be an integer, got {type(value).__name__}")
    return value


def _require_float(section: str, key: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{section}.{key} must be a number, got {type(value).__name__}")
    return float(value)


def _require_str_list(section: str, key: str, value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ConfigError(f"{section}.{key} must be a list, got {type(value).__name__}")
    result: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str):
            raise ConfigError(
                f"{section}.{key}[{index}] must be a string, got {type(item).__name__}"
            )
        result.append(item)
    return tuple(result)


def _parse_general(data: dict[str, Any]) -> GeneralConfig:
    _validate_unknown_keys("general", data, _GENERAL_KEYS)
    format_value = "markdown"
    min_confidence = "medium"
    output: str | None = None

    if "format" in data:
        format_value = _require_str("general", "format", data["format"]).lower()
        if format_value not in _VALID_FORMATS:
            raise ConfigError(
                f"general.format must be one of {sorted(_VALID_FORMATS)}, got {format_value!r}"
            )
    if "min_confidence" in data:
        min_confidence = _require_str(
            "general", "min_confidence", data["min_confidence"]
        ).lower()
        if min_confidence not in _VALID_MIN_CONFIDENCE:
            raise ConfigError(
                "general.min_confidence must be one of "
                f"{sorted(_VALID_MIN_CONFIDENCE)}, got {min_confidence!r}"
            )
    if "output" in data:
        output = _require_str("general", "output", data["output"])

    return GeneralConfig(
        format=format_value,
        min_confidence=min_confidence,
        output=output,
    )


def _parse_ignore(data: dict[str, Any]) -> IgnoreConfig:
    _validate_unknown_keys("ignore", data, _IGNORE_KEYS)
    paths: tuple[str, ...] = ()
    files: tuple[str, ...] = ()
    if "paths" in data:
        paths = _require_str_list("ignore", "paths", data["paths"])
    if "files" in data:
        files = _require_str_list("ignore", "files", data["files"])
    return IgnoreConfig(paths=paths, files=files)


def _parse_thresholds(data: dict[str, Any]) -> ThresholdsConfig:
    _validate_unknown_keys("thresholds", data, _THRESHOLDS_KEYS)
    max_hotspots = MAX_CHURN_FILES
    entropy_cutoff = ENTROPY_THRESHOLD

    if "max_hotspots" in data:
        max_hotspots = _require_int("thresholds", "max_hotspots", data["max_hotspots"])
        if max_hotspots < 1:
            raise ConfigError("thresholds.max_hotspots must be >= 1")
    if "entropy_cutoff" in data:
        entropy_cutoff = _require_float(
            "thresholds", "entropy_cutoff", data["entropy_cutoff"]
        )
        if entropy_cutoff <= 0:
            raise ConfigError("thresholds.entropy_cutoff must be > 0")

    return ThresholdsConfig(
        max_hotspots=max_hotspots,
        entropy_cutoff=entropy_cutoff,
    )


def _parse_secret_pattern(index: int, data: object) -> SecretPatternConfig:
    if not isinstance(data, dict):
        raise ConfigError(
            f"secrets.custom_patterns[{index}] must be a table, "
            f"got {type(data).__name__}"
        )
    _validate_unknown_keys(f"secrets.custom_patterns[{index}]", data, _SECRET_PATTERN_KEYS)
    missing = _SECRET_PATTERN_KEYS - set(data)
    if missing:
        joined = ", ".join(sorted(missing))
        raise ConfigError(f"secrets.custom_patterns[{index}] missing required key(s): {joined}")

    name = _require_str(f"secrets.custom_patterns[{index}]", "name", data["name"])
    regex_text = _require_str(f"secrets.custom_patterns[{index}]", "regex", data["regex"])
    confidence_raw = _require_str(
        f"secrets.custom_patterns[{index}]", "confidence", data["confidence"]
    )
    try:
        confidence = parse_confidence(confidence_raw)
    except ValueError as exc:
        raise ConfigError(str(exc)) from exc
    try:
        compiled = re.compile(regex_text)
    except re.error as exc:
        raise ConfigError(
            f"secrets.custom_patterns[{index}].regex is invalid: {exc}"
        ) from exc

    return SecretPatternConfig(name=name, regex=compiled, confidence=confidence)


def _parse_secrets(data: dict[str, Any]) -> SecretsConfig:
    _validate_unknown_keys("secrets", data, _SECRETS_KEYS)
    patterns: list[SecretPatternConfig] = []
    if "custom_patterns" in data:
        raw_patterns = data["custom_patterns"]
        if not isinstance(raw_patterns, list):
            raise ConfigError(
                "secrets.custom_patterns must be a list, "
                f"got {type(raw_patterns).__name__}"
            )
        for index, item in enumerate(raw_patterns):
            patterns.append(_parse_secret_pattern(index, item))
    return SecretsConfig(custom_patterns=tuple(patterns))


def _parse_vulnerabilities(data: dict[str, Any]) -> VulnerabilitiesConfig:
    _validate_unknown_keys("vulnerabilities", data, _VULNERABILITIES_KEYS)
    skip_osv = False
    if "skip_osv" in data:
        skip_osv = _require_bool("vulnerabilities", "skip_osv", data["skip_osv"])
    return VulnerabilitiesConfig(skip_osv=skip_osv)


def _parse_plugins(data: dict[str, Any]) -> PluginsConfig:
    _validate_unknown_keys("plugins", data, _PLUGINS_KEYS)
    disabled: tuple[str, ...] = ()
    if "disabled" in data:
        disabled = _require_str_list("plugins", "disabled", data["disabled"])
    return PluginsConfig(disabled=disabled)


def _parse_config_data(data: dict[str, Any]) -> RebriefConfig:
    _validate_unknown_keys("root", data, _KNOWN_TOP_LEVEL_KEYS)

    general = _parse_general(data["general"]) if "general" in data else GeneralConfig()
    if "general" in data and not isinstance(data["general"], dict):
        raise ConfigError("general must be a table")

    ignore = _parse_ignore(data["ignore"]) if "ignore" in data else IgnoreConfig()
    if "ignore" in data and not isinstance(data["ignore"], dict):
        raise ConfigError("ignore must be a table")

    thresholds = (
        _parse_thresholds(data["thresholds"])
        if "thresholds" in data
        else ThresholdsConfig()
    )
    if "thresholds" in data and not isinstance(data["thresholds"], dict):
        raise ConfigError("thresholds must be a table")

    secrets = _parse_secrets(data["secrets"]) if "secrets" in data else SecretsConfig()
    if "secrets" in data and not isinstance(data["secrets"], dict):
        raise ConfigError("secrets must be a table")

    vulnerabilities = (
        _parse_vulnerabilities(data["vulnerabilities"])
        if "vulnerabilities" in data
        else VulnerabilitiesConfig()
    )
    if "vulnerabilities" in data and not isinstance(data["vulnerabilities"], dict):
        raise ConfigError("vulnerabilities must be a table")

    plugins = _parse_plugins(data["plugins"]) if "plugins" in data else PluginsConfig()
    if "plugins" in data and not isinstance(data["plugins"], dict):
        raise ConfigError("plugins must be a table")

    return RebriefConfig(
        general=general,
        ignore=ignore,
        thresholds=thresholds,
        secrets=secrets,
        vulnerabilities=vulnerabilities,
        plugins=plugins,
    )


def build_extra_ignore_patterns(config: RebriefConfig) -> tuple[str, ...]:
    return config.ignore.paths + config.ignore.files


def load_config(
    repo_root: str | Path,
    explicit_path: str | Path | None = None,
) -> RebriefConfig:
    root = Path(repo_root).resolve()

    if explicit_path is not None:
        path = Path(explicit_path).expanduser()
        if not path.is_absolute():
            path = (Path.cwd() / path).resolve()
        if not path.is_file():
            raise ConfigError(f"Config file not found: {path}")
        parsed = _parse_config_data(_read_toml(path))
        return RebriefConfig(
            general=parsed.general,
            ignore=parsed.ignore,
            thresholds=parsed.thresholds,
            secrets=parsed.secrets,
            vulnerabilities=parsed.vulnerabilities,
            plugins=parsed.plugins,
            source_paths=(path,),
        )

    merged: dict[str, Any] = {}
    sources: list[Path] = []

    base_path = root / REBRIEF_CONFIG_FILENAME
    if base_path.is_file():
        merged = _read_toml(base_path)
        sources.append(base_path)

    dot_path = root / DOT_REBRIEF_CONFIG_FILENAME
    if dot_path.is_file():
        dot_data = _read_toml(dot_path)
        merged = _deep_merge_dicts(merged, dot_data)
        sources.append(dot_path)

    if not sources:
        return RebriefConfig()

    parsed = _parse_config_data(merged)
    return RebriefConfig(
        general=parsed.general,
        ignore=parsed.ignore,
        thresholds=parsed.thresholds,
        secrets=parsed.secrets,
        vulnerabilities=parsed.vulnerabilities,
        plugins=parsed.plugins,
        source_paths=tuple(sources),
    )


def resolve_effective_settings(
    config: RebriefConfig,
    cli: CliOverrides,
    *,
    default_output: str | None = None,
) -> EffectiveScanSettings:
    format_value = (
        cli.format.lower()
        if cli.format is not None
        else config.general.format
    )
    min_confidence = (
        cli.min_confidence.lower()
        if cli.min_confidence is not None
        else config.general.min_confidence
    )
    if cli.output is not None:
        output = cli.output
    elif config.general.output is not None:
        output = config.general.output
    else:
        output = default_output

    skip_vulnerability_check = (
        cli.skip_vulnerability_check
        if cli.skip_vulnerability_check is not None
        else config.vulnerabilities.skip_osv
    )

    parse_min_confidence(min_confidence)

    return EffectiveScanSettings(
        format=format_value,
        min_confidence=min_confidence,
        output=output,
        skip_vulnerability_check=skip_vulnerability_check,
        max_churn_files=config.thresholds.max_hotspots,
        extra_ignore_patterns=build_extra_ignore_patterns(config),
        entropy_cutoff=config.thresholds.entropy_cutoff,
        custom_secret_patterns=config.secrets.custom_patterns,
        disabled_plugins=config.plugins.disabled,
    )
