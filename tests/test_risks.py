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
