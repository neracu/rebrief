from pathlib import Path

from rebrief.parsers.risks import RisksParser


def test_missing_tests_flagged(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("print('ok')\n", encoding="utf-8")

    result = RisksParser(str(tmp_path)).parse()

    assert result["missing_tests"] is True


def test_tests_dir_present(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_app.py").write_text("def test_ok():\n    pass\n", encoding="utf-8")

    result = RisksParser(str(tmp_path)).parse()

    assert result["missing_tests"] is False


def test_detects_markers(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "module.py").write_text(
        "def run():\n    pass  # TODO fix this\n",
        encoding="utf-8",
    )

    result = RisksParser(str(tmp_path)).parse()

    assert result["markers"] == [
        {"file": "module.py", "line": 2, "marker": "TODO"}
    ]


def test_detects_secrets(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "config.py").write_text(
        'api_key = "abcdefghijklmnop"\n',
        encoding="utf-8",
    )

    result = RisksParser(str(tmp_path)).parse()

    assert result["secrets"] == [{"file": "config.py", "line": 1}]


def test_respects_cursorignore(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / ".cursorignore").write_text("ignored.py\n", encoding="utf-8")
    (tmp_path / "ignored.py").write_text("# TODO hidden\n", encoding="utf-8")
    (tmp_path / "visible.py").write_text("# FIXME visible\n", encoding="utf-8")

    result = RisksParser(str(tmp_path)).parse()

    assert result["markers"] == [
        {"file": "visible.py", "line": 1, "marker": "FIXME"}
    ]


def test_skips_binary_files(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "cache.pyc").write_bytes(b"\x00TODO")
    (tmp_path / "blob.bin").write_bytes(b"\x00\xffTODO")

    result = RisksParser(str(tmp_path)).parse()

    assert result["markers"] == []
    assert result["secrets"] == []


def test_requirements_version_conflict(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "requirements.txt").write_text(
        "django==4.2\ndjango==3.2\nrequests>=2.28\n",
        encoding="utf-8",
    )

    result = RisksParser(str(tmp_path)).parse()

    assert result["dependency_conflicts"] == [
        {"package": "django", "versions": ["==3.2", "==4.2"]}
    ]


def test_package_json_version_conflict(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "package.json").write_text(
        """{
  "dependencies": {
    "react": "^18.0.0"
  },
  "devDependencies": {
    "react": "^17.0.0"
  }
}""",
        encoding="utf-8",
    )

    result = RisksParser(str(tmp_path)).parse()

    assert result["dependency_conflicts"] == [
        {"package": "react", "versions": ["^17.0.0", "^18.0.0"]}
    ]


def test_clean_repo_minimal_risks(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_app.py").write_text(
        "def test_ok():\n    assert True\n",
        encoding="utf-8",
    )
    (tmp_path / "app.py").write_text("def main():\n    return 0\n", encoding="utf-8")

    result = RisksParser(str(tmp_path)).parse()

    assert result["missing_tests"] is False
    assert result["markers"] == []
    assert result["secrets"] == []
    assert result["dependency_conflicts"] == []


def test_skips_node_modules_markers(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    node_modules = tmp_path / "node_modules" / "lib"
    node_modules.mkdir(parents=True)
    (node_modules / "index.js").write_text("// TODO vendor noise\n", encoding="utf-8")

    result = RisksParser(str(tmp_path)).parse()

    assert result["markers"] == []


def test_skips_staticfiles_markers(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    staticfiles = tmp_path / "backend" / "staticfiles"
    staticfiles.mkdir(parents=True)
    (staticfiles / "admin.js").write_text("// TODO admin asset\n", encoding="utf-8")

    result = RisksParser(str(tmp_path)).parse()

    assert result["markers"] == []


def test_skips_static_vendor_markers(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    vendor = tmp_path / "static" / "vendor"
    vendor.mkdir(parents=True)
    (vendor / "jquery.js").write_text("// TODO jquery\n", encoding="utf-8")

    result = RisksParser(str(tmp_path)).parse()

    assert result["markers"] == []


def test_skips_min_js_and_md(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    src = tmp_path / "src"
    src.mkdir()
    (src / "app.min.js").write_text("// TODO minified\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# TODO readme\n", encoding="utf-8")

    result = RisksParser(str(tmp_path)).parse()

    assert result["markers"] == []


def test_skips_non_manifest_json(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    data = tmp_path / "data"
    data.mkdir()
    (data / "config.json").write_text('{"note": "TODO fix config"}\n', encoding="utf-8")

    result = RisksParser(str(tmp_path)).parse()

    assert result["markers"] == []


def test_skips_next_build_markers(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    next_dir = tmp_path / ".next" / "server"
    next_dir.mkdir(parents=True)
    (next_dir / "page.js").write_text("// TODO next build artifact\n", encoding="utf-8")

    result = RisksParser(str(tmp_path)).parse()

    assert result["markers"] == []


def test_skips_turbo_cache_markers(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    turbo_dir = tmp_path / ".turbo" / "cache"
    turbo_dir.mkdir(parents=True)
    (turbo_dir / "output.js").write_text("// TODO turbo cache\n", encoding="utf-8")

    result = RisksParser(str(tmp_path)).parse()

    assert result["markers"] == []


def test_scans_source_directories(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    source = tmp_path / "frontend" / "src"
    source.mkdir(parents=True)
    (source / "app.py").write_text("def run():\n    pass  # TODO ship feature\n", encoding="utf-8")

    result = RisksParser(str(tmp_path)).parse()

    assert result["markers"] == [
        {"file": "frontend/src/app.py", "line": 2, "marker": "TODO"}
    ]
