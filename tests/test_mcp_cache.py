from pathlib import Path

import pytest

from rebrief.mcp.cache import ScanCache, cache_path, compute_fingerprint
from rebrief.mcp.service import ScanService, resolve_repo_path


def _write_app(repo: Path, body: str = "print('ok')\n") -> None:
    (repo / "app.py").write_text(body, encoding="utf-8")


def test_fingerprint_stable_when_unchanged(tmp_path: Path) -> None:
    _write_app(tmp_path)
    first = compute_fingerprint(tmp_path)
    second = compute_fingerprint(tmp_path)
    assert first == second
    assert len(first) == 64


def test_fingerprint_changes_when_file_changes(tmp_path: Path) -> None:
    _write_app(tmp_path, "print(1)\n")
    before = compute_fingerprint(tmp_path)
    _write_app(tmp_path, "print(12345)\n")
    after = compute_fingerprint(tmp_path)
    assert before != after


def test_fingerprint_ignores_rebrief_cache_dir(tmp_path: Path) -> None:
    _write_app(tmp_path)
    before = compute_fingerprint(tmp_path)
    cache_dir = tmp_path / ".rebrief"
    cache_dir.mkdir()
    (cache_dir / "cache.json").write_text('{"version": 1}\n', encoding="utf-8")
    after = compute_fingerprint(tmp_path)
    assert before == after


def test_memory_cache_hit_skips_rescan(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_app(tmp_path)
    calls = {"n": 0}
    from rebrief.mcp import service as service_mod

    original = service_mod.run_scan

    def wrapped(*args: object, **kwargs: object):
        calls["n"] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(service_mod, "run_scan", wrapped)
    service = ScanService()
    service.get_tech_stack(str(tmp_path))
    service.get_tech_stack(str(tmp_path))
    assert calls["n"] == 1


def test_disk_cache_hit_across_instances(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_app(tmp_path)
    ScanService().get_tech_stack(str(tmp_path))
    assert cache_path(tmp_path).is_file()

    from rebrief.mcp import service as service_mod

    def fail_scan(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("scan should not run on a warm disk cache")

    monkeypatch.setattr(service_mod, "run_scan", fail_scan)
    ScanService(ScanCache()).get_tech_stack(str(tmp_path))


def test_force_refresh_rescans(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_app(tmp_path)
    calls = {"n": 0}
    from rebrief.mcp import service as service_mod

    original = service_mod.run_scan

    def wrapped(*args: object, **kwargs: object):
        calls["n"] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(service_mod, "run_scan", wrapped)
    service = ScanService()
    service.get_repository_brief(str(tmp_path))
    service.get_repository_brief(str(tmp_path), force_refresh=True)
    assert calls["n"] == 2


def test_file_change_invalidates_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_app(tmp_path, "print('a')\n")
    calls = {"n": 0}
    from rebrief.mcp import service as service_mod

    original = service_mod.run_scan

    def wrapped(*args: object, **kwargs: object):
        calls["n"] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(service_mod, "run_scan", wrapped)
    service = ScanService()
    service.get_tech_stack(str(tmp_path))
    _write_app(tmp_path, "print('changed-content')\n")
    service.get_tech_stack(str(tmp_path))
    assert calls["n"] == 2


def test_corrupt_disk_cache_is_ignored(tmp_path: Path) -> None:
    _write_app(tmp_path)
    cache_dir = tmp_path / ".rebrief"
    cache_dir.mkdir()
    (cache_dir / "cache.json").write_text("{not-json", encoding="utf-8")
    result = ScanCache().get(tmp_path)
    assert result is None


def test_resolve_repo_path_missing(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="does not exist"):
        resolve_repo_path(str(tmp_path / "missing"))


def test_resolve_repo_path_not_directory(tmp_path: Path) -> None:
    file_path = tmp_path / "notes.txt"
    file_path.write_text("x\n", encoding="utf-8")
    with pytest.raises(NotADirectoryError, match="not a directory"):
        resolve_repo_path(str(file_path))


def test_resolve_repo_path_empty() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        resolve_repo_path("  ")
