from __future__ import annotations

import os
import re
import subprocess
import tempfile
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager, nullcontext
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse, urlunparse

CLONE_DEPTH = 100
CLONE_ERROR_MESSAGE = (
    "Unable to access remote repository. Check the URL or your Git authentication "
    "credentials."
)

_SHORTHAND_RE = re.compile(r"^([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)$")
_SSH_SCP_RE = re.compile(r"^git@([^:]+):(.+)$")
_NOISE_SEGMENTS = frozenset(
    {
        "-",
        "actions",
        "blob",
        "commit",
        "commits",
        "issues",
        "merge_requests",
        "pipelines",
        "projects",
        "pull",
        "pulls",
        "raw",
        "releases",
        "src",
        "tree",
        "wiki",
    }
)


class RemoteCloneError(Exception):
    """Raised when a remote repository cannot be cloned."""


@dataclass(frozen=True)
class RemoteTarget:
    clone_url: str
    display_name: str


def _strip_git_suffix(segment: str) -> str:
    if segment.endswith(".git"):
        return segment[:-4]
    return segment


def _normalize_repo_segments(path: str) -> list[str] | None:
    trimmed = path.strip().strip("/")
    if not trimmed:
        return None
    segments: list[str] = []
    for raw in trimmed.split("/"):
        if not raw or raw in _NOISE_SEGMENTS:
            if raw in _NOISE_SEGMENTS:
                break
            continue
        segments.append(_strip_git_suffix(raw))
    if len(segments) < 2 or not all(segments):
        return None
    return segments


def parse_git_url(value: str) -> RemoteTarget | None:
    """Parse an explicit HTTPS/HTTP or SSH git URL, or return ``None``."""
    stripped = value.strip()
    if not stripped:
        return None

    ssh_match = _SSH_SCP_RE.match(stripped)
    if ssh_match is not None:
        host = ssh_match.group(1)
        segments = _normalize_repo_segments(ssh_match.group(2))
        if segments is None:
            return None
        path = "/".join(segments)
        return RemoteTarget(clone_url=f"git@{host}:{path}.git", display_name=path)

    parsed = urlparse(stripped)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or not parsed.path:
        return None
    segments = _normalize_repo_segments(parsed.path)
    if segments is None:
        return None
    path = "/".join(segments)
    clone_url = urlunparse((parsed.scheme, parsed.netloc, f"/{path}", "", "", ""))
    return RemoteTarget(clone_url=clone_url, display_name=path)


def parse_github_shorthand(value: str) -> RemoteTarget | None:
    """Parse GitHub ``owner/repo`` shorthand, or return ``None``."""
    stripped = value.strip()
    if stripped.startswith(".") or stripped.startswith("~"):
        return None
    match = _SHORTHAND_RE.match(stripped)
    if match is None:
        return None
    owner = match.group(1)
    repo = _strip_git_suffix(match.group(2))
    if not repo:
        return None
    display_name = f"{owner}/{repo}"
    return RemoteTarget(
        clone_url=f"https://github.com/{display_name}",
        display_name=display_name,
    )


def resolve_remote_target(value: str) -> RemoteTarget | None:
    """Return a remote target for git URLs or GitHub shorthand.

    Explicit URLs win. Existing local directories are never treated as
    shorthand remotes.
    """
    stripped = value.strip()
    explicit = parse_git_url(stripped)
    if explicit is not None:
        return explicit
    if Path(stripped).is_dir():
        return None
    return parse_github_shorthand(stripped)


def _is_ssh_clone_url(url: str) -> bool:
    return url.startswith("git@") or url.startswith("ssh://")


def build_clone_command(url: str) -> list[str]:
    """Build ``git clone`` argv (without the destination path)."""
    command = ["git"]
    if not _is_ssh_clone_url(url):
        token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GIT_AUTH_TOKEN")
        if token:
            command.extend(
                ["-c", f"http.extraHeader=Authorization: Bearer {token}"]
            )
    command.extend(
        [
            "clone",
            "--depth",
            str(CLONE_DEPTH),
            "--single-branch",
            "--quiet",
            url,
        ]
    )
    return command


def clone_remote(url: str, dest: Path) -> None:
    """Shallow-clone ``url`` into ``dest`` or raise ``RemoteCloneError``."""
    command = [*build_clone_command(url), str(dest)]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except (FileNotFoundError, subprocess.CalledProcessError, OSError) as exc:
        raise RemoteCloneError(CLONE_ERROR_MESSAGE) from exc


@contextmanager
def temporary_clone(
    target: RemoteTarget,
    *,
    status: Callable[[], AbstractContextManager[object]] | None = None,
) -> Iterator[Path]:
    """Clone ``target`` into a temp directory and delete it on exit."""
    tmp = tempfile.TemporaryDirectory(prefix="rebrief-")
    dest = Path(tmp.name)
    try:
        progress = status() if status is not None else nullcontext()
        with progress:
            clone_remote(target.clone_url, dest)
        yield dest
    finally:
        try:
            tmp.cleanup()
        except OSError:
            pass
