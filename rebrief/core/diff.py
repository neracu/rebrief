from __future__ import annotations

import subprocess
from pathlib import Path
from typing import TypedDict

DEFAULT_DIFF_REF = "HEAD~1"


class DiffScope(TypedDict):
    ref: str
    files: list[str]
    files_scanned: int
    files_total: int


class DiffError(Exception):
    """Raised when a diff scope cannot be resolved."""


def _run_git(repo_path: Path, args: list[str]) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise DiffError(
            "git is not installed or not available on PATH."
        ) from exc

    if result.returncode != 0:
        stderr = (result.stderr or result.stdout or "").strip()
        raise DiffError(stderr or f"git {' '.join(args)} failed.")
    return result.stdout


def count_tracked_files(repo_path: str | Path) -> int:
    """Return the number of files tracked by git, or 0 if unavailable."""
    path = Path(repo_path)
    if not (path / ".git").exists():
        return 0
    try:
        output = _run_git(path, ["ls-files"])
    except DiffError:
        return 0
    return sum(1 for line in output.splitlines() if line.strip())


def resolve_diff_scope(repo_path: str | Path, ref: str) -> DiffScope:
    """Resolve changed files for ``ref...HEAD`` into a DiffScope."""
    path = Path(repo_path)
    if not (path / ".git").exists():
        raise DiffError(f"Not a git repository: {path.resolve()}")

    try:
        _run_git(path, ["rev-parse", "--verify", ref])
    except DiffError as exc:
        message = str(exc)
        if "unknown revision" in message.lower() or "bad revision" in message.lower():
            raise DiffError(f"Unknown git ref: {ref}") from exc
        raise DiffError(f"Unknown git ref: {ref}") from exc

    try:
        diff_output = _run_git(path, ["diff", "--name-only", f"{ref}...HEAD"])
    except DiffError as exc:
        raise DiffError(
            f"Failed to compute diff against {ref}: {exc}"
        ) from exc

    files: list[str] = []
    for line in diff_output.splitlines():
        relative = line.strip().replace("\\", "/")
        if not relative:
            continue
        candidate = path / relative
        if candidate.is_file():
            files.append(relative)

    files = sorted(set(files))
    files_total = count_tracked_files(path)

    return {
        "ref": ref,
        "files": files,
        "files_scanned": len(files),
        "files_total": files_total,
    }
