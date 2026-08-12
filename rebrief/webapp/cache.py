from __future__ import annotations

import json
import os
import threading
from collections import OrderedDict
from typing import Protocol

from rebrief.webapp.schemas import ScanResponse

CACHE_MAXSIZE = 256
CACHE_TTL_SECONDS = 7 * 24 * 60 * 60
REDIS_PREFIX = "rebrief:scan:"


class ScanCache(Protocol):
    def get(self, key: str) -> ScanResponse | None: ...

    def put(self, key: str, value: ScanResponse) -> None: ...


class MemoryCache:
    """Thread-safe in-memory LRU cache."""

    def __init__(self, maxsize: int = CACHE_MAXSIZE) -> None:
        self._maxsize = maxsize
        self._data: OrderedDict[str, ScanResponse] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> ScanResponse | None:
        with self._lock:
            value = self._data.get(key)
            if value is None:
                return None
            self._data.move_to_end(key)
            return value.model_copy(deep=True)

    def put(self, key: str, value: ScanResponse) -> None:
        stored = value.model_copy(deep=True)
        stored.cached = False
        with self._lock:
            self._data[key] = stored
            self._data.move_to_end(key)
            while len(self._data) > self._maxsize:
                self._data.popitem(last=False)


class RedisCache:
    def __init__(self, url: str, ttl: int = CACHE_TTL_SECONDS) -> None:
        import redis

        self._client = redis.Redis.from_url(url)
        self._ttl = ttl

    def get(self, key: str) -> ScanResponse | None:
        raw = self._client.get(f"{REDIS_PREFIX}{key}")
        if not raw:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        data = json.loads(raw)
        return ScanResponse.model_validate(data)

    def put(self, key: str, value: ScanResponse) -> None:
        stored = value.model_copy(deep=True)
        stored.cached = False
        self._client.setex(
            f"{REDIS_PREFIX}{key}",
            self._ttl,
            stored.model_dump_json(),
        )


def cache_key(
    clone_url: str,
    commit_sha: str,
    min_confidence: str,
    diff_ref: str | None,
) -> str:
    return f"{clone_url}:{commit_sha}:{min_confidence}:{diff_ref or ''}"


def build_cache() -> ScanCache:
    redis_url = os.environ.get("REDIS_URL", "").strip()
    if redis_url:
        return RedisCache(redis_url)
    return MemoryCache()
