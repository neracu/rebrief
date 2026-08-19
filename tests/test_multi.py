from pathlib import Path
import json
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from rebrief.cli import main
from rebrief.core.remote import CLONE_ERROR_MESSAGE, RemoteCloneError


def _seed_repo(path: Path, *, framework: str) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "tests").mkdir(exist_ok=True)
    (path / "tests" / "test_app.py").write_text(
        "def test_ok() -> None:\n    pass\n",
        encoding="utf-8",
    )
    if framework == "next":
        (path / "package.json").write_text(
            '{"dependencies": {"next": "^14.0.0", "react": "^18.2.0"}}',
            encoding="utf-8",
        )
    elif framework == "fastapi":
        (path / "requirements.txt").write_text("fastapi==0.110.0\n", encoding="utf-8")
    elif framework == "infra":
        (path / "Dockerfile").write_text("FROM alpine\n", encoding="utf-8")


def test_multi_help() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["multi", "--help"])
    assert result.exit_code == 0
    assert "TARGETS" in result.output
    assert "--format" in result.output
    assert "--skip-vulnerability-check" in result.output


def test_main_help_lists_multi() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "multi" in result.output


def test_multi_two_local_targets(tmp_path: Path) -> None:
    frontend = tmp_path / "frontend"
    backend = tmp_path / "backend"
    _seed_repo(frontend, framework="next")
    _seed_repo(backend, framework="fastapi")

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(
            main,
            ["multi", str(frontend), str(backend)],
        )
        assert result.exit_code == 0, result.output
        assert Path("REBRIEF-SYSTEM.md").is_file()
        content = Path("REBRIEF-SYSTEM.md").read_text(encoding="utf-8")
        assert "# REBRIEF SYSTEM REPORT" in content
        assert "## Service: frontend" in content
        assert "## Service: backend" in content
        assert "Next.js" in content or "React" in content
        assert "FastAPI" in content


def test_multi_json_output(tmp_path: Path) -> None:
    frontend = tmp_path / "frontend"
    backend = tmp_path / "backend"
    _seed_repo(frontend, framework="next")
    _seed_repo(backend, framework="fastapi")

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(
            main,
            ["multi", str(frontend), str(backend), "-f", "json"],
        )
        assert result.exit_code == 0, result.output
        payload = json.loads(Path("REBRIEF-SYSTEM.json").read_text(encoding="utf-8"))
        assert payload["kind"] == "system"
        assert payload["summary"]["services_count"] == 2


def test_multi_workspace_expansion(tmp_path: Path) -> None:
    root = tmp_path / "mono"
    root.mkdir()
    (root / "pnpm-workspace.yaml").write_text(
        "packages:\n  - packages/*\n",
        encoding="utf-8",
    )
    (root / "packages").mkdir()
    web = root / "packages" / "web"
    api = root / "packages" / "api"
    _seed_repo(web, framework="next")
    (web / "package.json").write_text(
        '{"dependencies": {"react": "^18.2.0"}}',
        encoding="utf-8",
    )
    _seed_repo(api, framework="fastapi")
    (api / "package.json").write_text(
        '{"dependencies": {"react": "^17.0.2"}}',
        encoding="utf-8",
    )

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(main, ["multi", str(root)])
        assert result.exit_code == 0, result.output
        content = Path("REBRIEF-SYSTEM.md").read_text(encoding="utf-8")
        assert "## Service: web" in content
        assert "## Service: api" in content
        assert "Mismatch" in content or "react" in content


def test_multi_mixed_local_and_remote(tmp_path: Path) -> None:
    local = tmp_path / "frontend"
    _seed_repo(local, framework="next")

    def fake_clone(url: str, dest: Path, **kwargs: object) -> None:
        _seed_repo(dest, framework="fastapi")

    runner = CliRunner()
    with patch("rebrief.core.remote.clone_remote", fake_clone):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(
                main,
                ["multi", str(local), "owner/backend"],
            )
            assert result.exit_code == 0, result.output
            assert Path("REBRIEF-SYSTEM.md").is_file()
            assert "Fetching remote repository [owner/backend]" in result.output


def test_multi_remote_clone_failure() -> None:
    def boom(url: str, dest: Path, **kwargs: object) -> None:
        raise RemoteCloneError(CLONE_ERROR_MESSAGE)

    runner = CliRunner()
    with patch("rebrief.core.remote.clone_remote", boom):
        result = runner.invoke(main, ["multi", "owner/repo"])
    assert result.exit_code == 1
    assert "Unable to access remote repository" in result.output


def test_multi_missing_local_path() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["multi", "not-a-directory"])
    assert result.exit_code == 1
    assert "does not exist" in result.output
