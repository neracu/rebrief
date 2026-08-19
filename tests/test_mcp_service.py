from pathlib import Path
from contextlib import contextmanager
from collections.abc import Iterator
import subprocess

import pytest

from rebrief.core.remote import CLONE_ERROR_MESSAGE, RemoteCloneError, RemoteTarget
from rebrief.mcp.service import ScanService, format_rebrief_context


def _seed_repo(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_app.py").write_text(
        "def test_ok() -> None:\n    pass\n",
        encoding="utf-8",
    )
    (tmp_path / "requirements.txt").write_text("django==4.2\nclick>=8.1\n", encoding="utf-8")
    (tmp_path / "app.py").write_text("# TODO: tighten validation\nprint(1)\n", encoding="utf-8")


def test_get_repository_brief_returns_markdown(tmp_path: Path) -> None:
    _seed_repo(tmp_path)
    markdown = ScanService().get_repository_brief(str(tmp_path))
    assert markdown.startswith("# REBRIEF REPORT:")
    assert "Technology Stack" in markdown or "Languages" in markdown
    assert "django" in markdown.lower() or "Python" in markdown


def test_get_tech_stack_shape(tmp_path: Path) -> None:
    _seed_repo(tmp_path)
    stack = ScanService().get_tech_stack(str(tmp_path))
    assert stack["languages"] == ["Python"]
    assert "requirements.txt" in stack["manifests"]
    assert any("django" in dep.lower() for dep in stack["dependencies"])
    assert "frameworks" in stack


def test_get_risk_map_shape_and_confidence_filter(tmp_path: Path) -> None:
    _seed_repo(tmp_path)
    service = ScanService()
    medium = service.get_risk_map(str(tmp_path), min_confidence="medium")
    assert set(medium.keys()) == {"critical", "warning", "info", "vulnerabilities"}
    high = service.get_risk_map(str(tmp_path), min_confidence="high")
    assert len(high["info"]) <= len(medium["info"])


def test_get_risk_map_invalid_confidence(tmp_path: Path) -> None:
    _seed_repo(tmp_path)
    with pytest.raises(ValueError, match="min-confidence"):
        ScanService().get_risk_map(str(tmp_path), min_confidence="nope")


def test_get_codebase_hotspots_from_git(tmp_path: Path) -> None:
    _seed_repo(tmp_path)

    def git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)

    git("init")
    git("config", "user.email", "test@example.com")
    git("config", "user.name", "Test User")
    git("add", ".")
    git("commit", "-m", "Initial import")
    (tmp_path / "app.py").write_text("# TODO: tighten validation\nprint(2)\n", encoding="utf-8")
    git("add", "app.py")
    git("commit", "-m", "Update app")

    hotspots = ScanService().get_codebase_hotspots(str(tmp_path), top_n=2)
    assert len(hotspots) <= 2
    assert all("file" in item and "changes" in item for item in hotspots)


def test_get_codebase_hotspots_rejects_non_positive_top_n(tmp_path: Path) -> None:
    _seed_repo(tmp_path)
    with pytest.raises(ValueError, match="top_n"):
        ScanService().get_codebase_hotspots(str(tmp_path), top_n=0)


def test_invalid_path_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        ScanService().get_tech_stack(str(tmp_path / "does-not-exist"))


def test_get_repository_brief_accepts_url(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_repo(tmp_path)
    calls = {"n": 0}

    @contextmanager
    def fake_clone(target: RemoteTarget, **kwargs: object) -> Iterator[Path]:
        calls["n"] += 1
        assert target.clone_url == "https://github.com/owner/repo"
        yield tmp_path

    monkeypatch.setattr("rebrief.mcp.service.temporary_clone", fake_clone)
    service = ScanService()
    markdown = service.get_repository_brief("https://github.com/owner/repo")
    assert markdown.startswith("# REBRIEF REPORT:")
    service.get_repository_brief("https://github.com/owner/repo")
    assert calls["n"] == 1
    service.get_repository_brief("https://github.com/owner/repo", force_refresh=True)
    assert calls["n"] == 2


def test_get_repository_brief_accepts_shorthand(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_repo(tmp_path)

    @contextmanager
    def fake_clone(target: RemoteTarget, **kwargs: object) -> Iterator[Path]:
        assert target.display_name == "owner/repo"
        yield tmp_path

    monkeypatch.setattr("rebrief.mcp.service.temporary_clone", fake_clone)
    markdown = ScanService().get_repository_brief("owner/repo")
    assert "REBRIEF" in markdown


def test_get_repository_brief_remote_clone_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    @contextmanager
    def boom(target: RemoteTarget, **kwargs: object) -> Iterator[Path]:
        raise RemoteCloneError(CLONE_ERROR_MESSAGE)
        yield Path(".")  # pragma: no cover

    monkeypatch.setattr("rebrief.mcp.service.temporary_clone", boom)
    with pytest.raises(RemoteCloneError, match="Unable to access remote repository"):
        ScanService().get_repository_brief("https://github.com/owner/repo")


def test_format_rebrief_context_template() -> None:
    text = format_rebrief_context("STACK AND RISKS")
    assert "STACK AND RISKS" in text
    assert text.startswith("You are assisting with a codebase.")
    assert "guide your changes safely" in text
