import subprocess
from pathlib import Path

import pytest

from rebrief.core.diff import DiffError, resolve_diff_scope
from rebrief.parsers.risks import RisksParser
from rebrief.parsers.stack import StackParser


def _run_git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )


def _init_repo(tmp_path: Path) -> Path:
    _run_git(tmp_path, "init")
    _run_git(tmp_path, "config", "user.email", "test@example.com")
    _run_git(tmp_path, "config", "user.name", "Test User")
    # Ensure HEAD~1 / branch names work on modern git defaults.
    _run_git(tmp_path, "checkout", "-b", "main")
    return tmp_path


def _commit_file(repo: Path, relative: str, content: str, message: str) -> None:
    path = repo / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    _run_git(repo, "add", relative)
    _run_git(repo, "commit", "-m", message)


def test_resolve_diff_scope_head_tilde(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _commit_file(repo, "a.py", "print(1)\n", "Add a")
    _commit_file(repo, "b.py", "print(2)\n", "Add b")

    scope = resolve_diff_scope(repo, "HEAD~1")

    assert scope["ref"] == "HEAD~1"
    assert scope["files"] == ["b.py"]
    assert scope["files_scanned"] == 1
    assert scope["files_total"] == 2


def test_resolve_diff_scope_named_ref(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _commit_file(repo, "base.py", "print('base')\n", "Base")
    _run_git(repo, "branch", "feature-base")
    _commit_file(repo, "feature.py", "print('feature')\n", "Feature")

    scope = resolve_diff_scope(repo, "feature-base")

    assert scope["ref"] == "feature-base"
    assert scope["files"] == ["feature.py"]
    assert scope["files_scanned"] == 1
    assert scope["files_total"] == 2


def test_resolve_diff_scope_excludes_deleted_files(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _commit_file(repo, "keep.py", "print('keep')\n", "Add keep")
    _commit_file(repo, "gone.py", "print('gone')\n", "Add gone")
    _run_git(repo, "rm", "gone.py")
    _run_git(repo, "commit", "-m", "Remove gone")
    (repo / "new.py").write_text("print('new')\n", encoding="utf-8")
    _run_git(repo, "add", "new.py")
    _run_git(repo, "commit", "-m", "Add new")

    scope = resolve_diff_scope(repo, "HEAD~2")

    assert "gone.py" not in scope["files"]
    assert "new.py" in scope["files"]
    assert all((repo / path).is_file() for path in scope["files"])


def test_resolve_diff_scope_not_a_git_repo(tmp_path: Path) -> None:
    with pytest.raises(DiffError, match="Not a git repository"):
        resolve_diff_scope(tmp_path, "HEAD~1")


def test_resolve_diff_scope_unknown_ref(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _commit_file(repo, "a.py", "print(1)\n", "Add a")

    with pytest.raises(DiffError, match="Unknown git ref"):
        resolve_diff_scope(repo, "does-not-exist")


def test_stack_parser_paths_skips_unlisted_manifests(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text("django==4.2\n", encoding="utf-8")
    (tmp_path / "package.json").write_text(
        '{"dependencies": {"react": "18.0.0"}}', encoding="utf-8"
    )

    result = StackParser(str(tmp_path), paths=["requirements.txt"]).parse()

    assert result["manifests"] == ["requirements.txt"]
    assert "django" in result["dependencies"]
    assert not any("react" in dep for dep in result["dependencies"])


def test_risks_parser_paths_only_scans_allowlist(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "changed.py").write_text("# TODO: fix me\n", encoding="utf-8")
    (tmp_path / "other.py").write_text("# TODO: ignore me\n", encoding="utf-8")

    result = RisksParser(str(tmp_path), paths=["changed.py"]).parse()

    assert len(result["markers"]) == 1
    assert result["markers"][0]["file"] == "changed.py"
    assert result["missing_tests"] is False
