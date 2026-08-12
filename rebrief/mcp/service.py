from __future__ import annotations

from pathlib import Path

from rebrief.core.confidence import Confidence, meets_threshold, parse_min_confidence
from rebrief.core.remote import RemoteTarget, resolve_remote_target, temporary_clone
from rebrief.core.reporter import ReportHotspot, ReportRiskItem, ReportRiskMap, ReportTechStack
from rebrief.core.scan import run_scan
from rebrief.mcp.cache import (
    CACHE_VERSION,
    MCP_HOTSPOT_LIMIT,
    CacheEntry,
    ScanCache,
    compute_fingerprint,
)

_CONFIDENCE_RANK: dict[Confidence, int] = {
    Confidence.HIGH: 3,
    Confidence.MEDIUM: 2,
    Confidence.LOW: 1,
}

REBRIEF_CONTEXT_TEMPLATE = (
    "You are assisting with a codebase. Here is the latest Rebrief summary "
    "of architectural hotspots and risks: {summary}. Use this to guide your "
    "changes safely."
)


def resolve_repo_path(path: str) -> Path:
    """Resolve ``path`` to an existing directory or raise."""
    if not path or not str(path).strip():
        raise ValueError("Path must be a non-empty directory.")
    resolved = Path(path).expanduser()
    try:
        resolved = resolved.resolve()
    except OSError as exc:
        raise FileNotFoundError(f"Path does not exist: {path}") from exc
    if not resolved.exists():
        raise FileNotFoundError(f"Path does not exist: {path}")
    if not resolved.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {path}")
    return resolved


def filter_risk_map(risk_map: ReportRiskMap, minimum: Confidence) -> ReportRiskMap:
    def keep(items: list[ReportRiskItem]) -> list[ReportRiskItem]:
        return [
            item
            for item in items
            if meets_threshold(Confidence(item["confidence"]), minimum)
        ]

    return {
        "critical": keep(risk_map["critical"]),
        "warning": keep(risk_map["warning"]),
        "info": keep(risk_map["info"]),
    }


def format_rebrief_context(summary: str) -> str:
    return REBRIEF_CONTEXT_TEMPLATE.format(summary=summary)


class ScanService:
    """Cached scan helpers used by MCP tools, resources, and prompts."""

    def __init__(self, cache: ScanCache | None = None) -> None:
        self._cache = cache or ScanCache()
        self._remote_memory: dict[str, CacheEntry] = {}

    def get_snapshot(
        self,
        path: str = ".",
        *,
        min_confidence: str = "medium",
        force_refresh: bool = False,
    ) -> CacheEntry:
        remote = resolve_remote_target(path)
        if remote is not None:
            return self._snapshot_remote(
                remote, min_confidence, force_refresh=force_refresh
            )

        repo = resolve_repo_path(path)
        confidence = parse_min_confidence(min_confidence)
        fingerprint = compute_fingerprint(repo)

        if not force_refresh:
            cached = self._cache.get(repo, fingerprint)
            if cached is not None and not _needs_rescan(cached, confidence):
                return cached

        return self._scan_and_store(repo, confidence, fingerprint)

    def get_repository_brief(
        self, path: str = ".", force_refresh: bool = False
    ) -> str:
        return self.get_snapshot(path, force_refresh=force_refresh)["markdown"]

    def get_risk_map(
        self, path: str = ".", min_confidence: str = "medium"
    ) -> ReportRiskMap:
        confidence = parse_min_confidence(min_confidence)
        entry = self.get_snapshot(path, min_confidence=min_confidence)
        return filter_risk_map(entry["payload"]["risk_map"], confidence)

    def get_codebase_hotspots(
        self, path: str = ".", top_n: int = 10
    ) -> list[ReportHotspot]:
        if top_n < 1:
            raise ValueError("top_n must be >= 1")
        entry = self.get_snapshot(path)
        return list(entry["hotspots"][:top_n])

    def get_tech_stack(self, path: str = ".") -> ReportTechStack:
        return entry_tech_stack(self.get_snapshot(path))

    def _snapshot_remote(
        self,
        remote: RemoteTarget,
        min_confidence: str,
        *,
        force_refresh: bool,
    ) -> CacheEntry:
        confidence = parse_min_confidence(min_confidence)
        key = remote.clone_url
        if not force_refresh:
            cached = self._remote_memory.get(key)
            if cached is not None and not _needs_rescan(cached, confidence):
                return cached

        with temporary_clone(remote) as repo:
            entry = self._scan_and_store(
                repo,
                confidence,
                f"remote:{key}",
                persist=False,
            )
        self._remote_memory[key] = entry
        return entry

    def _scan_and_store(
        self,
        repo: Path,
        confidence: Confidence,
        fingerprint: str,
        *,
        persist: bool = True,
    ) -> CacheEntry:
        generator = run_scan(
            repo,
            confidence,
            max_churn_files=MCP_HOTSPOT_LIMIT,
        )
        payload = generator.to_dict()
        entry: CacheEntry = {
            "version": CACHE_VERSION,
            "fingerprint": fingerprint,
            "min_confidence": confidence.value.lower(),
            "markdown": generator.generate(),
            "payload": payload,
            "hotspots": list(payload["timeline"]["hotspots"]),
        }
        if persist:
            self._cache.put(repo, entry)
        return entry


def entry_tech_stack(entry: CacheEntry) -> ReportTechStack:
    return entry["payload"]["tech_stack"]


def _needs_rescan(cached: CacheEntry, requested: Confidence) -> bool:
    try:
        cached_confidence = parse_min_confidence(cached["min_confidence"])
    except ValueError:
        return True
    return _CONFIDENCE_RANK[requested] < _CONFIDENCE_RANK[cached_confidence]
