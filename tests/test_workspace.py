from pathlib import Path

import pytest

from rebrief.core.workspace import (
    detect_workspace_patterns,
    expand_workspace_members,
    path_matches_prefix,
)


def test_no_workspace_returns_single_member(tmp_path: Path) -> None:
    members = expand_workspace_members(tmp_path, source=".")
    assert len(members) == 1
    assert members[0]["name"] == tmp_path.name
    assert members[0]["source"] == "."
    assert members[0]["git_root"] is None


def test_pnpm_workspace_expansion(tmp_path: Path) -> None:
    (tmp_path / "apps").mkdir()
    (tmp_path / "apps" / "web").mkdir()
    (tmp_path / "apps" / "api").mkdir()
    (tmp_path / "pnpm-workspace.yaml").write_text(
        "packages:\n  - 'apps/*'\n  - '!apps/legacy'\n",
        encoding="utf-8",
    )

    patterns = detect_workspace_patterns(tmp_path)
    assert patterns == ["apps/*"]

    members = expand_workspace_members(tmp_path, source=".")
    names = {member["name"] for member in members}
    assert names == {"web", "api"}


def test_lerna_workspace_expansion(tmp_path: Path) -> None:
    (tmp_path / "packages").mkdir()
    (tmp_path / "packages" / "ui").mkdir()
    (tmp_path / "packages" / "core").mkdir()
    (tmp_path / "lerna.json").write_text(
        '{"packages": ["packages/*"]}',
        encoding="utf-8",
    )

    members = expand_workspace_members(tmp_path, source=".")
    names = {member["name"] for member in members}
    assert names == {"ui", "core"}


def test_npm_workspaces_expansion(tmp_path: Path) -> None:
    (tmp_path / "frontend").mkdir()
    (tmp_path / "backend").mkdir()
    (tmp_path / "package.json").write_text(
        '{"name": "mono", "workspaces": ["frontend", "backend"]}',
        encoding="utf-8",
    )

    members = expand_workspace_members(tmp_path, source=".")
    names = {member["name"] for member in members}
    assert names == {"frontend", "backend"}


def test_cargo_workspace_expansion(tmp_path: Path) -> None:
    (tmp_path / "crates").mkdir()
    (tmp_path / "crates" / "api").mkdir()
    (tmp_path / "crates" / "cli").mkdir()
    (tmp_path / "Cargo.toml").write_text(
        '[workspace]\nmembers = ["crates/*"]\nexclude = ["crates/legacy"]\n',
        encoding="utf-8",
    )

    members = expand_workspace_members(tmp_path, source=".")
    names = {member["name"] for member in members}
    assert names == {"api", "cli"}


def test_git_root_set_when_dot_git_present(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    (tmp_path / "packages").mkdir()
    (tmp_path / "packages" / "web").mkdir()
    (tmp_path / "pnpm-workspace.yaml").write_text(
        "packages:\n  - packages/*\n",
        encoding="utf-8",
    )

    members = expand_workspace_members(tmp_path, source=".")
    web = next(member for member in members if member["name"] == "web")
    assert web["git_root"] == str(tmp_path.resolve())
    assert web["path_prefix"] == "packages/web/"


def test_path_matches_prefix() -> None:
    assert path_matches_prefix("packages/web/src/app.ts", "packages/web/")
    assert not path_matches_prefix("packages/api/src/app.ts", "packages/web/")
