from html.parser import HTMLParser
from pathlib import Path

from rebrief import __version__
from rebrief.core.confidence import Confidence
from rebrief.core.reporter import ReportGenerator
from rebrief.parsers.git_log import GitLogResult
from rebrief.parsers.risks import RiskReport
from rebrief.parsers.stack import StackResult
from tests.test_reporter import _make_generator, make_report_data


class _RecordingParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tags: list[str] = []
        self.script_srcs: list[str] = []
        self.link_hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append(tag)
        attr = dict(attrs)
        if tag == "script" and attr.get("src"):
            self.script_srcs.append(attr["src"] or "")
        if tag == "link" and attr.get("href"):
            self.link_hrefs.append(attr["href"] or "")


def test_generate_html_structure_and_scan_data(tmp_path: Path) -> None:
    html = _make_generator(tmp_path).generate_html()

    assert html.strip()
    assert html.startswith("<!DOCTYPE html>")
    assert "<style>" in html
    assert "</style>" in html
    assert "<script>" in html
    assert "</script>" in html
    assert 'src="' not in html
    assert "cdn." not in html.lower()
    assert "googleapis" not in html.lower()

    assert "demo-repo" in html
    assert "Python" in html
    assert "Django" in html
    assert "pyproject.toml" in html
    assert "src/app.py" in html
    assert "Hard-coded secret in config.py:3" in html
    assert "Missing tests directory" in html
    assert "Review and rotate hard-coded credentials" in html
    assert "Token efficiency" in html
    assert "Brief tokens" in html
    assert "Read the following REBRIEF.md" in html
    assert f"v{__version__}" in html

    assert 'id="copy-prompt-btn"' in html
    assert "Copy Prompt for AI" in html
    assert "Dashboard View" in html
    assert "Raw Markdown View" in html
    assert 'id="risk-search"' in html
    assert ">All<" in html
    assert ">CRITICAL<" in html
    assert ">WARNING<" in html
    assert ">INFO<" in html
    assert ">HIGH<" in html
    assert ">MEDIUM<" in html
    assert 'data-severity="CRITICAL"' in html
    assert 'data-confidence="MEDIUM"' in html
    assert 'data-sort="file"' in html
    assert 'id="raw-md"' in html


def test_generate_html_parses(tmp_path: Path) -> None:
    html = _make_generator(tmp_path).generate_html()
    parser = _RecordingParser()
    parser.feed(html)
    parser.close()
    assert "html" in parser.tags
    assert "style" in parser.tags
    assert "script" in parser.tags
    assert parser.script_srcs == []
    assert parser.link_hrefs == []


def test_generate_html_escapes_special_characters(tmp_path: Path) -> None:
    stack: StackResult = {
        "languages": ["C++"],
        "manifests": ["a&b.xml"],
        "frameworks": ["Foo<Bar>"],
        "dependencies": ["pkg>=1&2"],
        "is_empty": False,
        "manifest_warnings": [],
    }
    git_log: GitLogResult = {
        "commits": [],
        "top_modified_files": [{"file": "src/a&b.ts", "count": 2}],
        "status_message": None,
    }
    risks: RiskReport = {
        "missing_tests": False,
        "markers": [],
        "secrets": [{"file": "cfg<x>.py", "line": 1, "confidence": "HIGH"}],
        "dependency_conflicts": [],
    }
    html = ReportGenerator(
        str(tmp_path / "escape-repo"), stack, {}, git_log, risks
    ).generate_html()

    assert "Foo<Bar>" not in html
    assert "cfg<x>.py" not in html
    assert "a&b.xml" not in html
    assert "Foo&lt;Bar&gt;" in html
    assert "cfg&lt;x&gt;.py" in html
    assert "a&amp;b.xml" in html
    assert "src/a&amp;b.ts" in html
    assert "pkg&gt;=1&amp;2" in html


def test_write_html_report_creates_file(tmp_path: Path) -> None:
    output_path = tmp_path / "REBRIEF.html"
    generator = _make_generator(tmp_path)

    generator.write_html_report(output_path)

    html = output_path.read_text(encoding="utf-8")
    assert html.startswith("<!DOCTYPE html>")
    assert "Django" in html
    assert "<style>" in html
    assert "<script>" in html


def test_generate_html_includes_info_when_confidence_low(tmp_path: Path) -> None:
    stack, rules, git_log, risks = make_report_data()
    html = ReportGenerator(
        str(tmp_path / "demo-repo"),
        stack,
        rules,
        git_log,
        risks,
        min_confidence=Confidence.LOW,
    ).generate_html()

    assert "TODO in app.py:10" in html
    assert 'data-severity="INFO"' in html
    assert 'data-confidence="LOW"' in html
