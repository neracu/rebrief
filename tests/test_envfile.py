from __future__ import annotations

from pathlib import Path

import pytest

from rebrief.chat.credentials import resolve_auth
from rebrief.core.envfile import find_env_file, load_env_files


def test_load_env_file_does_not_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "from-process")
    (tmp_path / ".env").write_text("OPENROUTER_API_KEY=from-file\n", encoding="utf-8")
    loaded = load_env_files(tmp_path)
    assert loaded == tmp_path / ".env"
    assert os_get("OPENROUTER_API_KEY") == "from-process"


def test_load_env_file_fills_missing_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    (tmp_path / ".git").mkdir()
    (tmp_path / ".env").write_text(
        "# comment\n"
        "export OPENROUTER_API_KEY='sk-or-from-dotenv'\n"
        "OTHER = quoted\n",
        encoding="utf-8",
    )
    loaded = load_env_files(tmp_path)
    assert loaded == tmp_path / ".env"
    assert os_get("OPENROUTER_API_KEY") == "sk-or-from-dotenv"
    auth = resolve_auth(model="openrouter/openai/gpt-4o-mini")
    assert auth.api_key == "sk-or-from-dotenv"


def test_find_env_stops_at_git_root(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    nested = tmp_path / "src" / "pkg"
    nested.mkdir(parents=True)
    assert find_env_file(nested) is None
    (tmp_path / ".env").write_text("OPENROUTER_API_KEY=nested\n", encoding="utf-8")
    assert find_env_file(nested) == tmp_path / ".env"


def os_get(name: str) -> str:
    import os

    return os.environ.get(name, "")
