from pathlib import Path

from rebrief.parsers.stack import StackParser


def test_empty_repo(tmp_path: Path) -> None:
    result = StackParser(str(tmp_path)).parse()

    assert set(result.keys()) == {"languages", "manifests", "frameworks", "dependencies"}
    assert result["languages"] == []
    assert result["manifests"] == []
    assert result["frameworks"] == []
    assert result["dependencies"] == []


def test_python_requirements(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text(
        "django==4.2\nrequests>=2.28\n# comment\n-r other.txt\n",
        encoding="utf-8",
    )

    result = StackParser(str(tmp_path)).parse()

    assert result["languages"] == ["Python"]
    assert result["manifests"] == ["requirements.txt"]
    assert "django" in result["dependencies"]
    assert "requests" in result["dependencies"]


def test_python_pyproject(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        """[project]
name = "demo"
dependencies = [
    "click>=8.1",
    "colorama>=0.4",
]
""",
        encoding="utf-8",
    )

    result = StackParser(str(tmp_path)).parse()

    assert result["languages"] == ["Python"]
    assert result["manifests"] == ["pyproject.toml"]
    assert "click>=8.1" in result["dependencies"]


def test_node_package_json(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        """{
  "dependencies": {
    "react": "^18.0.0"
  },
  "devDependencies": {
    "typescript": "^5.0.0"
  }
}""",
        encoding="utf-8",
    )

    result = StackParser(str(tmp_path)).parse()

    assert result["languages"] == ["JavaScript/TypeScript"]
    assert result["manifests"] == ["package.json"]
    assert "react" in result["dependencies"]
    assert "typescript" in result["dependencies"]


def test_go_mod(tmp_path: Path) -> None:
    (tmp_path / "go.mod").write_text("module example.com/demo\n", encoding="utf-8")

    result = StackParser(str(tmp_path)).parse()

    assert result["languages"] == ["Go"]
    assert result["manifests"] == ["go.mod"]


def test_cargo_toml(tmp_path: Path) -> None:
    (tmp_path / "Cargo.toml").write_text(
        '[package]\nname = "demo"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )

    result = StackParser(str(tmp_path)).parse()

    assert result["languages"] == ["Rust"]
    assert result["manifests"] == ["Cargo.toml"]


def test_framework_signatures(tmp_path: Path) -> None:
    (tmp_path / "manage.py").write_text("# django\n", encoding="utf-8")
    (tmp_path / "vite.config.js").write_text("export default {}\n", encoding="utf-8")

    result = StackParser(str(tmp_path)).parse()

    assert "Django" in result["frameworks"]
    assert "Vite" in result["frameworks"]


def test_next_config_mjs(tmp_path: Path) -> None:
    (tmp_path / "next.config.mjs").write_text("export default {}\n", encoding="utf-8")

    result = StackParser(str(tmp_path)).parse()

    assert result["frameworks"] == ["Next.js"]


def test_combined_stack(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        '{"dependencies": {"react": "^18.0.0"}}',
        encoding="utf-8",
    )
    (tmp_path / "pyproject.toml").write_text(
        '[project]\ndependencies = ["click>=8.1"]\n',
        encoding="utf-8",
    )
    (tmp_path / "manage.py").write_text("# django\n", encoding="utf-8")

    result = StackParser(str(tmp_path)).parse()

    assert "JavaScript/TypeScript" in result["languages"]
    assert "Python" in result["languages"]
    assert "package.json" in result["manifests"]
    assert "pyproject.toml" in result["manifests"]
    assert "Django" in result["frameworks"]
    assert "react" in result["dependencies"]
    assert "click>=8.1" in result["dependencies"]


def test_nested_frontend_package_json(tmp_path: Path) -> None:
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "package.json").write_text(
        '{"dependencies": {"react": "^18.0.0"}}',
        encoding="utf-8",
    )

    result = StackParser(str(tmp_path)).parse()

    assert result["manifests"] == ["frontend/package.json"]
    assert "React" in result["frameworks"]
    assert "react" in result["dependencies"]


def test_nested_backend_requirements(tmp_path: Path) -> None:
    backend = tmp_path / "backend"
    backend.mkdir()
    (backend / "requirements.txt").write_text("django==4.2\n", encoding="utf-8")

    result = StackParser(str(tmp_path)).parse()

    assert result["manifests"] == ["backend/requirements.txt"]
    assert "Django" in result["frameworks"]
    assert "django" in result["dependencies"]


def test_nested_next_dependency(tmp_path: Path) -> None:
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "package.json").write_text(
        '{"dependencies": {"next": "^14.0.0"}}',
        encoding="utf-8",
    )

    result = StackParser(str(tmp_path)).parse()

    assert "Next.js" in result["frameworks"]


def test_djangorestframework_in_requirements(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text(
        "djangorestframework==3.14.0\n",
        encoding="utf-8",
    )

    result = StackParser(str(tmp_path)).parse()

    assert "Django REST Framework" in result["frameworks"]


def test_skips_node_modules(tmp_path: Path) -> None:
    node_modules = tmp_path / "node_modules" / "ignored"
    node_modules.mkdir(parents=True)
    (node_modules / "package.json").write_text(
        '{"dependencies": {"react": "^18.0.0"}}',
        encoding="utf-8",
    )

    result = StackParser(str(tmp_path)).parse()

    assert result["manifests"] == []
    assert "React" not in result["frameworks"]


def test_depth_limit_excludes_deep_files(tmp_path: Path) -> None:
    deep_dir = tmp_path / "a" / "b" / "c" / "d"
    deep_dir.mkdir(parents=True)
    (deep_dir / "package.json").write_text(
        '{"dependencies": {"react": "^18.0.0"}}',
        encoding="utf-8",
    )

    result = StackParser(str(tmp_path)).parse()

    assert result["manifests"] == []
    assert "React" not in result["frameworks"]
