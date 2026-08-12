import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from rebrief.core.remote import (
    CLONE_DEPTH,
    CLONE_ERROR_MESSAGE,
    RemoteCloneError,
    RemoteTarget,
    build_clone_command,
    clone_remote,
    fetch_remote_head,
    parse_git_url,
    parse_github_shorthand,
    resolve_remote_target,
    temporary_clone,
)


@pytest.mark.parametrize(
    ("value", "clone_url", "display_name"),
    [
        (
            "https://github.com/owner/repo",
            "https://github.com/owner/repo",
            "owner/repo",
        ),
        (
            "https://github.com/owner/repo.git",
            "https://github.com/owner/repo",
            "owner/repo",
        ),
        (
            "https://github.com/owner/repo/",
            "https://github.com/owner/repo",
            "owner/repo",
        ),
        (
            "https://github.com/owner/repo/tree/main",
            "https://github.com/owner/repo",
            "owner/repo",
        ),
        (
            "https://gitlab.com/owner/repo",
            "https://gitlab.com/owner/repo",
            "owner/repo",
        ),
        (
            "https://gitlab.com/group/sub/repo.git",
            "https://gitlab.com/group/sub/repo",
            "group/sub/repo",
        ),
        (
            "git@github.com:owner/repo.git",
            "git@github.com:owner/repo.git",
            "owner/repo",
        ),
        (
            "git@gitlab.com:group/repo",
            "git@gitlab.com:group/repo.git",
            "group/repo",
        ),
    ],
)
def test_parse_git_url(value: str, clone_url: str, display_name: str) -> None:
    target = parse_git_url(value)
    assert target == RemoteTarget(clone_url=clone_url, display_name=display_name)


def test_parse_git_url_rejects_local_paths() -> None:
    assert parse_git_url(".") is None
    assert parse_git_url("/tmp/repo") is None
    assert parse_git_url("owner/repo") is None


def test_parse_github_shorthand() -> None:
    assert parse_github_shorthand("owner/repo") == RemoteTarget(
        clone_url="https://github.com/owner/repo",
        display_name="owner/repo",
    )
    assert parse_github_shorthand("owner/repo.git") == RemoteTarget(
        clone_url="https://github.com/owner/repo",
        display_name="owner/repo",
    )
    assert parse_github_shorthand("./owner/repo") is None
    assert parse_github_shorthand("group/sub/repo") is None
    assert parse_github_shorthand("not-a-repo") is None


def test_resolve_remote_target_prefers_existing_local_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    local = tmp_path / "owner" / "repo"
    local.mkdir(parents=True)
    assert resolve_remote_target(str(local)) is None
    monkeypatch.chdir(tmp_path)
    assert resolve_remote_target("owner/repo") is None


def test_resolve_remote_target_shorthand_when_missing() -> None:
    target = resolve_remote_target("octocat/hello-world")
    assert target is not None
    assert target.clone_url == "https://github.com/octocat/hello-world"
    assert target.display_name == "octocat/hello-world"


def test_resolve_remote_target_explicit_url_wins() -> None:
    target = resolve_remote_target("https://github.com/owner/repo")
    assert target is not None
    assert target.display_name == "owner/repo"


def test_build_clone_command_shallow_flags() -> None:
    command = build_clone_command("https://github.com/owner/repo")
    assert command[0] == "git"
    assert "--depth" in command
    assert str(CLONE_DEPTH) in command
    assert "--single-branch" in command
    assert "--quiet" in command
    assert command[-1] == "https://github.com/owner/repo"


def test_https_clone_adds_bearer_from_github_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "secret-token")
    monkeypatch.delenv("GIT_AUTH_TOKEN", raising=False)
    command = build_clone_command("https://github.com/owner/repo")
    assert "http.extraHeader=Authorization: Bearer secret-token" in command


def test_https_clone_uses_git_auth_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setenv("GIT_AUTH_TOKEN", "gitlab-token")
    command = build_clone_command("https://gitlab.com/owner/repo")
    assert "http.extraHeader=Authorization: Bearer gitlab-token" in command


def test_ssh_clone_skips_token_header(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "secret-token")
    command = build_clone_command("git@github.com:owner/repo.git")
    assert all("extraHeader" not in part for part in command)


@patch("rebrief.core.remote.subprocess.run")
def test_clone_remote_passes_dest_and_flags(
    mock_run: MagicMock, tmp_path: Path
) -> None:
    mock_run.return_value = MagicMock(returncode=0)
    clone_remote("https://github.com/owner/repo", tmp_path)
    command = mock_run.call_args.args[0]
    assert "--depth" in command
    assert "100" in command
    assert "--single-branch" in command
    assert str(tmp_path) == command[-1]
    mock_run.assert_called_once()


@patch("rebrief.core.remote.subprocess.run")
def test_clone_remote_failure_message(mock_run: MagicMock, tmp_path: Path) -> None:
    mock_run.side_effect = subprocess.CalledProcessError(128, ["git"])
    with pytest.raises(RemoteCloneError, match=CLONE_ERROR_MESSAGE):
        clone_remote("https://github.com/owner/repo", tmp_path)


@patch("rebrief.core.remote.subprocess.run")
def test_clone_remote_missing_git(mock_run: MagicMock, tmp_path: Path) -> None:
    mock_run.side_effect = FileNotFoundError("git")
    with pytest.raises(RemoteCloneError, match=CLONE_ERROR_MESSAGE):
        clone_remote("https://github.com/owner/repo", tmp_path)


def test_temporary_clone_cleans_up_on_success() -> None:
    captured: dict[str, Path] = {}

    def fake_clone(url: str, dest: Path, **kwargs: object) -> None:
        captured["dest"] = dest
        dest.joinpath("README.md").write_text("ok\n", encoding="utf-8")

    target = RemoteTarget(
        clone_url="https://github.com/owner/repo",
        display_name="owner/repo",
    )
    with patch("rebrief.core.remote.clone_remote", fake_clone):
        with temporary_clone(target) as repo:
            assert repo.exists()
            assert (repo / "README.md").is_file()
            captured["during"] = repo
    assert not captured["dest"].exists()
    assert not captured["during"].exists()


def test_temporary_clone_cleans_up_on_failure() -> None:
    captured: dict[str, Path] = {}

    def boom(url: str, dest: Path, **kwargs: object) -> None:
        captured["dest"] = dest
        dest.joinpath("partial").write_text("x\n", encoding="utf-8")
        raise RemoteCloneError(CLONE_ERROR_MESSAGE)

    target = RemoteTarget(
        clone_url="https://github.com/owner/repo",
        display_name="owner/repo",
    )
    with patch("rebrief.core.remote.clone_remote", boom):
        with pytest.raises(RemoteCloneError, match=CLONE_ERROR_MESSAGE):
            with temporary_clone(target):
                raise AssertionError("clone should fail before yield")
    assert "dest" in captured
    assert not captured["dest"].exists()


def test_build_clone_command_custom_depth() -> None:
    command = build_clone_command("https://github.com/owner/repo", depth=50)
    depth_index = command.index("--depth")
    assert command[depth_index + 1] == "50"
    assert str(CLONE_DEPTH) not in command


def test_build_clone_command_unauthenticated_skips_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "secret-token")
    command = build_clone_command(
        "https://github.com/owner/repo",
        authenticated=False,
    )
    assert all("extraHeader" not in part for part in command)


@patch("rebrief.core.remote.subprocess.run")
def test_clone_remote_custom_depth(mock_run: MagicMock, tmp_path: Path) -> None:
    mock_run.return_value = MagicMock(returncode=0)
    clone_remote("https://github.com/owner/repo", tmp_path, depth=50)
    command = mock_run.call_args.args[0]
    assert command[command.index("--depth") + 1] == "50"


@patch("rebrief.core.remote.subprocess.run")
def test_fetch_remote_head_parses_sha(mock_run: MagicMock) -> None:
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout="abc123def456\tHEAD\n",
    )
    sha = fetch_remote_head("https://github.com/owner/repo")
    assert sha == "abc123def456"
    command = mock_run.call_args.args[0]
    assert command[:3] == ["git", "ls-remote", "https://github.com/owner/repo"]
    assert all("extraHeader" not in part for part in command)


@patch("rebrief.core.remote.subprocess.run")
def test_fetch_remote_head_failure(mock_run: MagicMock) -> None:
    mock_run.side_effect = subprocess.CalledProcessError(128, ["git"])
    with pytest.raises(RemoteCloneError, match=CLONE_ERROR_MESSAGE):
        fetch_remote_head("https://github.com/owner/repo")


@patch("rebrief.core.remote.subprocess.run")
def test_fetch_remote_head_empty_output(mock_run: MagicMock) -> None:
    mock_run.return_value = MagicMock(returncode=0, stdout="\n")
    with pytest.raises(RemoteCloneError, match=CLONE_ERROR_MESSAGE):
        fetch_remote_head("https://github.com/owner/repo")
