from pathlib import Path

import pytest

from rebrief.core.confidence import Confidence, meets_threshold, parse_min_confidence
from rebrief.core.reporter import ReportGenerator, collected_items_from_risk_report
from rebrief.parsers.git_log import GitLogResult
from rebrief.parsers.risks import RisksParser
from rebrief.parsers.stack import StackResult
from tests.test_reporter import make_report_data


@pytest.mark.parametrize(
    ("item", "minimum", "expected"),
    [
        (Confidence.HIGH, Confidence.HIGH, True),
        (Confidence.MEDIUM, Confidence.HIGH, False),
        (Confidence.LOW, Confidence.MEDIUM, False),
        (Confidence.HIGH, Confidence.MEDIUM, True),
        (Confidence.MEDIUM, Confidence.MEDIUM, True),
        (Confidence.LOW, Confidence.LOW, True),
        (Confidence.MEDIUM, Confidence.LOW, True),
    ],
)
def test_meets_threshold(item: Confidence, minimum: Confidence, expected: bool) -> None:
    assert meets_threshold(item, minimum) is expected


def test_parse_min_confidence() -> None:
    assert parse_min_confidence("high") is Confidence.HIGH
    assert parse_min_confidence("MEDIUM") is Confidence.MEDIUM
    assert parse_min_confidence("low") is Confidence.LOW


def test_marker_findings_have_low_confidence(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "app.py").write_text("# TODO follow up\n", encoding="utf-8")

    result = RisksParser(str(tmp_path)).parse()

    assert result["markers"][0]["confidence"] == Confidence.LOW.value


def test_entropy_secret_has_medium_confidence(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "config.py").write_text(
        'api_key = "aB3xQ9mK7pL2wZ8vN4tR"\n',
        encoding="utf-8",
    )

    result = RisksParser(str(tmp_path)).parse()

    assert result["secrets"][0]["confidence"] == Confidence.MEDIUM.value


def test_format_secret_has_high_confidence(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "config.py").write_text(
        'ACCESS_KEY = "AKIAIOSFODNN7EXAMPLE"\n',
        encoding="utf-8",
    )

    result = RisksParser(str(tmp_path)).parse()

    assert result["secrets"][0]["confidence"] == Confidence.HIGH.value


def test_manifest_warning_has_high_confidence(tmp_path: Path) -> None:
    stack: StackResult = {
        "languages": ["PHP"],
        "manifests": ["composer.json"],
        "frameworks": [],
        "dependencies": [],
        "is_empty": False,
        "manifest_warnings": ["Malformed manifest: composer.json (parse error)"],
    }
    git_log: GitLogResult = {
        "commits": [],
        "top_modified_files": [],
        "status_message": None,
    }
    risks = {
        "missing_tests": False,
        "markers": [],
        "secrets": [],
        "dependency_conflicts": [],
    }
    generator = ReportGenerator(str(tmp_path / "repo"), stack, {}, git_log, collected_items_from_risk_report(risks))
    payload = generator.to_dict()

    assert payload["risk_map"]["warning"][0]["confidence"] == Confidence.HIGH.value


def test_dependency_conflict_has_medium_confidence(tmp_path: Path) -> None:
    stack, rules, git_log, risks = make_report_data()
    generator = ReportGenerator(
        str(tmp_path / "demo-repo"),
        stack,
        rules,
        git_log,
        collected_items_from_risk_report(risks),
        min_confidence=Confidence.LOW,
    )
    payload = generator.to_dict()

    conflict_items = [
        item
        for item in payload["risk_map"]["warning"]
        if item["message"].startswith("Duplicate dependency")
    ]
    assert conflict_items[0]["confidence"] == Confidence.MEDIUM.value


def test_default_min_confidence_hides_low_markers(tmp_path: Path) -> None:
    stack, rules, git_log, risks = make_report_data()
    generator = ReportGenerator(
        str(tmp_path / "demo-repo"),
        stack,
        rules,
        git_log,
        collected_items_from_risk_report(risks),
    )

    payload = generator.to_dict()

    assert payload["risk_map"]["info"] == []
    assert generator.filtered_risk_count() == 3


def test_low_min_confidence_includes_markers(tmp_path: Path) -> None:
    stack, rules, git_log, risks = make_report_data()
    generator = ReportGenerator(
        str(tmp_path / "demo-repo"),
        stack,
        rules,
        git_log,
        collected_items_from_risk_report(risks),
        min_confidence=Confidence.LOW,
    )

    payload = generator.to_dict()

    assert payload["risk_map"]["info"] == [
        {
            "message": "TODO in app.py:10",
            "confidence": Confidence.LOW.value,
        }
    ]
    assert generator.filtered_risk_count() == 4
