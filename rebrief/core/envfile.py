from __future__ import annotations

import os
from pathlib import Path

_MAX_PARENTS = 8


def load_env_files(start: str | Path | None = None) -> Path | None:
    """Load the nearest ``.env`` into ``os.environ`` without overriding existing keys.

    Returns the loaded path, or ``None`` if no file was found. Values are never logged.
    """
    path = find_env_file(start)
    if path is None:
        return None
    _apply_env_file(path)
    return path


def find_env_file(start: str | Path | None = None) -> Path | None:
    try:
        current = Path(start or Path.cwd()).expanduser().resolve()
    except OSError:
        return None
    if current.is_file():
        current = current.parent
    for _ in range(_MAX_PARENTS):
        candidate = current / ".env"
        if candidate.is_file():
            return candidate
        if (current / ".git").exists():
            return None
        parent = current.parent
        if parent == current:
            return None
        current = parent
    return None


def _apply_env_file(path: Path) -> None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key or not _valid_env_name(key):
            continue
        if key in os.environ:
            continue
        os.environ[key] = _unquote(value.strip())


def _valid_env_name(key: str) -> bool:
    if key[0].isdigit():
        return False
    return all(ch.isalnum() or ch == "_" for ch in key)


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value
