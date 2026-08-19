from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass
from importlib.metadata import entry_points
from pathlib import Path
from typing import TYPE_CHECKING

import click

from rebrief.plugins.base import BaseRiskDetector, RiskItem, ScanContext
from rebrief.plugins.builtin import BUILTIN_PLUGINS

if TYPE_CHECKING:
    from collections.abc import Sequence


@dataclass(frozen=True)
class PluginDescriptor:
    name: str
    description: str
    source: str
    plugin: BaseRiskDetector | None = None


def _warn(message: str) -> None:
    click.echo(f"[WARNING] {message}", err=True)


def _instantiate_plugin(
    target: type[BaseRiskDetector] | BaseRiskDetector,
) -> BaseRiskDetector:
    if isinstance(target, BaseRiskDetector):
        return target
    return target()


def _is_concrete_detector(candidate: type[object]) -> bool:
    return (
        isinstance(candidate, type)
        and issubclass(candidate, BaseRiskDetector)
        and candidate is not BaseRiskDetector
    )


def _find_detector_classes(module: object) -> list[type[BaseRiskDetector]]:
    detectors: list[type[BaseRiskDetector]] = []
    for value in vars(module).values():
        if _is_concrete_detector(value):
            detectors.append(value)
    return detectors


def _load_local_plugin(path: Path) -> list[BaseRiskDetector]:
    module_name = f"rebrief_local_plugin_{path.stem}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        _warn(f"Plugin load failed for '{path.name}': unable to create module spec")
        return []

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        _warn(f"Plugin load failed for '{path.name}': {exc}")
        return []

    plugins: list[BaseRiskDetector] = []
    for detector_cls in _find_detector_classes(module):
        try:
            plugins.append(_instantiate_plugin(detector_cls))
        except Exception as exc:
            _warn(
                f"Plugin load failed for '{path.name}' "
                f"({detector_cls.__name__}): {exc}"
            )
    return plugins


def _load_entry_point_plugins() -> list[tuple[str, BaseRiskDetector]]:
    plugins: list[tuple[str, BaseRiskDetector]] = []
    for entry_point in entry_points(group="rebrief.plugins"):
        try:
            loaded = entry_point.load()
            plugin = _instantiate_plugin(loaded)
            plugins.append((f"entry-point:{entry_point.name}", plugin))
        except Exception as exc:
            _warn(f"Plugin load failed for entry point '{entry_point.name}': {exc}")
    return plugins


def _discover_local_plugins(repo_path: Path) -> list[tuple[str, BaseRiskDetector]]:
    plugins_dir = repo_path / ".rebrief" / "plugins"
    if not plugins_dir.is_dir():
        return []

    discovered: list[tuple[str, BaseRiskDetector]] = []
    for path in sorted(plugins_dir.glob("*.py")):
        if path.name.startswith("_"):
            continue
        for plugin in _load_local_plugin(path):
            discovered.append((f".rebrief/plugins/{path.name}", plugin))
    return discovered


def instantiate_builtin_plugins() -> list[BaseRiskDetector]:
    return [_instantiate_plugin(plugin_cls) for plugin_cls in BUILTIN_PLUGINS]


def resolve_plugins(
    repo_path: str | Path,
    *,
    enable_external: bool = True,
    disabled: Sequence[str] = (),
) -> list[BaseRiskDetector]:
    disabled_set = {name.strip() for name in disabled if name.strip()}
    resolved: list[BaseRiskDetector] = []
    seen_names: set[str] = set()

    for plugin in instantiate_builtin_plugins():
        if plugin.name in disabled_set:
            continue
        resolved.append(plugin)
        seen_names.add(plugin.name)

    if enable_external:
        repo = Path(repo_path).resolve()
        external: list[tuple[str, BaseRiskDetector]] = []
        external.extend(_discover_local_plugins(repo))
        external.extend(_load_entry_point_plugins())

        for source, plugin in external:
            if plugin.name in disabled_set:
                continue
            if plugin.name in seen_names:
                _warn(
                    f"Plugin '{plugin.name}' from {source} skipped: "
                    "name already registered by a built-in plugin"
                )
                continue
            resolved.append(plugin)
            seen_names.add(plugin.name)

    return resolved


def list_plugin_descriptors(
    repo_path: str | Path,
    *,
    enable_external: bool = True,
    disabled: Sequence[str] = (),
) -> tuple[list[PluginDescriptor], list[PluginDescriptor]]:
    disabled_set = {name.strip() for name in disabled if name.strip()}
    builtin: list[PluginDescriptor] = []
    external: list[PluginDescriptor] = []

    for plugin_cls in BUILTIN_PLUGINS:
        plugin = _instantiate_plugin(plugin_cls)
        descriptor = PluginDescriptor(
            name=plugin.name,
            description=plugin.description,
            source="builtin",
            plugin=plugin,
        )
        if plugin.name in disabled_set:
            descriptor = PluginDescriptor(
                name=descriptor.name,
                description=descriptor.description,
                source=f"{descriptor.source} (disabled)",
                plugin=None,
            )
        builtin.append(descriptor)

    if not enable_external:
        return builtin, external

    repo = Path(repo_path).resolve()
    seen_names = {item.name for item in builtin}
    for source, plugin in _discover_local_plugins(repo):
        if plugin.name in seen_names:
            continue
        descriptor = PluginDescriptor(
            name=plugin.name,
            description=plugin.description,
            source=source,
            plugin=plugin,
        )
        if plugin.name in disabled_set:
            descriptor = PluginDescriptor(
                name=descriptor.name,
                description=descriptor.description,
                source=f"{descriptor.source} (disabled)",
                plugin=None,
            )
        external.append(descriptor)
        seen_names.add(plugin.name)

    for source, plugin in _load_entry_point_plugins():
        if plugin.name in seen_names:
            continue
        descriptor = PluginDescriptor(
            name=plugin.name,
            description=plugin.description,
            source=source,
            plugin=plugin,
        )
        if plugin.name in disabled_set:
            descriptor = PluginDescriptor(
                name=descriptor.name,
                description=descriptor.description,
                source=f"{descriptor.source} (disabled)",
                plugin=None,
            )
        external.append(descriptor)
        seen_names.add(plugin.name)

    return builtin, external


def format_plugin_list(
    builtin: Sequence[PluginDescriptor],
    external: Sequence[PluginDescriptor],
    *,
    external_disabled: bool = False,
) -> str:
    lines = ["Built-in plugins:"]
    for descriptor in builtin:
        lines.append(f"  {descriptor.name:<22} {descriptor.description}")
    lines.append("")
    lines.append("External plugins:")
    if external_disabled:
        lines.append("  (disabled via --no-plugins)")
    elif not external:
        lines.append("  (none)")
    else:
        for descriptor in external:
            lines.append(f"  {descriptor.name:<22} {descriptor.description}")
            lines.append(f"{'':24}(source: {descriptor.source})")
    return "\n".join(lines)


def run_risk_plugins(
    plugins: Sequence[BaseRiskDetector],
    context: ScanContext,
) -> list[RiskItem]:
    items: list[RiskItem] = []
    for plugin in plugins:
        try:
            items.extend(plugin.scan(context))
        except Exception as exc:
            _warn(f"Plugin '{plugin.name}' failed during execution: {exc}")
    return items
