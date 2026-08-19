from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from rebrief import __version__

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_IMAGE_TAG = "rebrief:integration-test"
CONTAINER_UID = 1000


def _docker_available() -> bool:
    return shutil.which("docker") is not None


def _docker_volume_path(path: Path) -> str:
    resolved = path.resolve()
    if sys.platform == "win32" and resolved.drive:
        return "/" + resolved.drive[0].lower() + resolved.as_posix()[2:]
    return str(resolved)


def _docker_run(
    image: str,
    args: list[str],
    *,
    workdir: Path | None = None,
    entrypoint: str | None = None,
) -> subprocess.CompletedProcess[str]:
    cmd = ["docker", "run", "--rm"]
    if entrypoint is not None:
        cmd.extend(["--entrypoint", entrypoint])
    if workdir is not None:
        cmd.extend(["-v", f"{_docker_volume_path(workdir)}:/app", "-w", "/app"])
    cmd.append(image)
    cmd.extend(args)
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


@pytest.fixture(scope="module")
def docker_image() -> str:
    if not _docker_available():
        pytest.skip("docker CLI not found")
    tag = os.environ.get("REBRIEF_DOCKER_IMAGE", DEFAULT_IMAGE_TAG)
    if os.environ.get("REBRIEF_DOCKER_IMAGE"):
        yield tag
        return
    build = subprocess.run(
        ["docker", "build", "-t", tag, str(REPO_ROOT)],
        capture_output=True,
        text=True,
    )
    if build.returncode != 0:
        pytest.skip(f"docker build failed: {build.stderr}")
    yield tag


@pytest.fixture
def scan_workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    tests_dir = workspace / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_app.py").write_text("def test_ok() -> None:\n    pass\n", encoding="utf-8")
    os.chmod(workspace, 0o777)
    for child in workspace.rglob("*"):
        if child.is_dir():
            os.chmod(child, 0o777)
    return workspace


@pytest.mark.docker
def test_docker_entrypoint_version(docker_image: str) -> None:
    result = _docker_run(docker_image, ["--version"])
    assert result.returncode == 0
    assert __version__ in result.stdout


@pytest.mark.docker
def test_docker_runs_as_non_root_user(docker_image: str) -> None:
    result = _docker_run(docker_image, ["-u"], entrypoint="id")
    assert result.returncode == 0
    uid = result.stdout.strip()
    assert uid == str(CONTAINER_UID)
    assert uid != "0"


@pytest.mark.docker
def test_docker_scan_mounted_volume_json(docker_image: str, scan_workspace: Path) -> None:
    result = _docker_run(
        docker_image,
        [
            "scan",
            ".",
            "-f",
            "json",
            "-o",
            "REBRIEF.json",
            "--skip-vulnerability-check",
        ],
        workdir=scan_workspace,
    )
    assert result.returncode == 0, result.stderr
    output_file = scan_workspace / "REBRIEF.json"
    assert output_file.is_file()
    payload = json.loads(output_file.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)


@pytest.mark.docker
def test_docker_scan_mounted_volume_markdown(docker_image: str, scan_workspace: Path) -> None:
    result = _docker_run(
        docker_image,
        ["scan", ".", "--skip-vulnerability-check"],
        workdir=scan_workspace,
    )
    assert result.returncode == 0, result.stderr
    assert (scan_workspace / "REBRIEF.md").is_file()


@pytest.mark.docker
def test_docker_default_cmd_scan(docker_image: str, scan_workspace: Path) -> None:
    result = _docker_run(docker_image, [], workdir=scan_workspace)
    assert result.returncode == 0, result.stderr
    assert (scan_workspace / "REBRIEF.md").is_file()
