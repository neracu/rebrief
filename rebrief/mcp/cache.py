from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import TypedDict

from rebrief.core.ignore import IgnoreMatcher, SUPPLEMENTAL_IGNORE_FILES
from rebrief.core.reporter import ReportHotspot, ReportPayload
from rebrief.parsers.stack import MAX_DEPTH

CACHE_DIRNAME = ".rebrief"
CACHE_FILENAME = "cache.json"
CACHE_VERSION = 1
MCP_HOTSPOT_LIMIT = 50


class CacheEntry(TypedDict):
    version: int
    fingerprint: str
    min_confidence: str
    markdown: str
    payload: ReportPayload
    hotspots: list[ReportHotspot]


def cache_path(repo: Path) -> Path:
    return repo / CACHE_DIRNAME / CACHE_FILENAME


def _git_head(repo: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError, OSError):
        return ""
    return result.stdout.strip()


def _file_stat_token(path: Path, relative: str) -> str:
    try:
        stat = path.stat()
    except OSError:
        return f"{relative}:missing"
    return f"{relative}:{stat.st_size}:{stat.st_mtime_ns}"


def _walk_file_tokens(repo: Path) -> list[str]:
    matcher = IgnoreMatcher(repo)
    tokens: list[str] = []

    for root, dirs, files in os.walk(repo):
        root_path = Path(root)
        relative_root = root_path.relative_to(repo)
        depth = len(relative_root.parts)
        relative_root_str = relative_root.as_posix() if relative_root.parts else ""
        dirs[:] = sorted(
            directory
            for directory in dirs
            if depth < MAX_DEPTH
            and not matcher.should_prune_dir(directory, relative_root_str)
        )
        for filename in sorted(files):
            file_path = root_path / filename
            relative = file_path.relative_to(repo).as_posix()
            tokens.append(_file_stat_token(file_path, relative))

    return tokens


def compute_fingerprint(repo: Path) -> str:
    hasher = hashlib.sha256()
    hasher.update(_git_head(repo).encode("utf-8"))
    hasher.update(b"\n")

    for ignore_name in SUPPLEMENTAL_IGNORE_FILES:
        hasher.update(_file_stat_token(repo / ignore_name, ignore_name).encode("utf-8"))
        hasher.update(b"\n")

    for token in _walk_file_tokens(repo):
        hasher.update(token.encode("utf-8"))
        hasher.update(b"\n")

    return hasher.hexdigest()


def _entry_from_json(raw: object) -> CacheEntry | None:
    if not isinstance(raw, dict):
        return None
    if raw.get("version") != CACHE_VERSION:
        return None
    fingerprint = raw.get("fingerprint")
    min_confidence = raw.get("min_confidence")
    markdown = raw.get("markdown")
    payload = raw.get("payload")
    hotspots = raw.get("hotspots")
    if not isinstance(fingerprint, str) or not fingerprint:
        return None
    if not isinstance(min_confidence, str):
        return None
    if not isinstance(markdown, str):
        return None
    if not isinstance(payload, dict):
        return None
    if not isinstance(hotspots, list):
        return None
    return {
        "version": CACHE_VERSION,
        "fingerprint": fingerprint,
        "min_confidence": min_confidence,
        "markdown": markdown,
        "payload": payload,  # type: ignore[typeddict-item]
        "hotspots": hotspots,  # type: ignore[typeddict-item]
    }


class ScanCache:
    """In-memory plus ``.rebrief/cache.json`` scan cache keyed by resolved path."""

    def __init__(self) -> None:
        self._memory: dict[str, CacheEntry] = {}

    def get(self, repo: Path, fingerprint: str | None = None) -> CacheEntry | None:
        key = str(repo)
        expected = fingerprint if fingerprint is not None else compute_fingerprint(repo)
        entry = self._memory.get(key)
        if entry is not None and entry["fingerprint"] == expected:
            return entry
        disk = self._read_disk(repo)
        if disk is not None and disk["fingerprint"] == expected:
            self._memory[key] = disk
            return disk
        return None

    def put(self, repo: Path, entry: CacheEntry) -> None:
        self._memory[str(repo)] = entry
        self._write_disk(repo, entry)

    def invalidate(self, repo: Path) -> None:
        self._memory.pop(str(repo), None)

    def _read_disk(self, repo: Path) -> CacheEntry | None:
        path = cache_path(repo)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return _entry_from_json(raw)

    def _write_disk(self, repo: Path, entry: CacheEntry) -> None:
        path = cache_path(repo)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(entry, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        except OSError:
            pass
