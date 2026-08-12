from __future__ import annotations

import os

from slowapi import Limiter
from slowapi.util import get_remote_address

DEFAULT_SCAN_LIMIT = "10/minute"


def scan_rate_limit() -> str:
    return os.environ.get("SCAN_RATE_LIMIT", DEFAULT_SCAN_LIMIT).strip() or DEFAULT_SCAN_LIMIT


def build_limiter() -> Limiter:
    redis_url = os.environ.get("REDIS_URL", "").strip()
    storage_uri = redis_url if redis_url else "memory://"
    return Limiter(
        key_func=get_remote_address,
        default_limits=[],
        storage_uri=storage_uri,
        headers_enabled=True,
    )
