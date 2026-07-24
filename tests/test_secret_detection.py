from pathlib import Path

import pytest

from rebrief.core.reporter import ReportGenerator
from rebrief.parsers.git_log import GitLogResult
from rebrief.parsers.risks import RisksParser
from rebrief.parsers.stack import StackResult

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "secrets"

EXPECTED_FINDINGS = [
    {"file": "aws_config.py", "line": 2},
    {"file": "openai_config.py", "line": 2},
    {"file": "api_keys.cfg", "line": 1},
    {"file": "app_config.py", "line": 2},
]


def test_secret_fixture_scan() -> None:
    result = RisksParser(str(FIXTURES_DIR)).parse()

    assert result["missing_tests"] is False
    assert sorted(result["secrets"], key=lambda item: item["file"]) == sorted(
        EXPECTED_FINDINGS,
        key=lambda item: item["file"],
    )


@pytest.mark.parametrize(
    ("source_line", "should_detect", "label"),
    [
        ('api_key = "abcdefghijklmnop"', True, "quoted api_key assignment"),
        ('password = "admin12345"', True, "short password assignment"),
        ('ACCESS_KEY = "AKIAIOSFODNN7EXAMPLE"', True, "AWS access key ID"),
        (
            'client_key = "sk-proj-fakefakefakefakefakefake12"',
            True,
            "OpenAI-style sk- key",
        ),
        ("API_KEY=sk-fakefakefakefakefakefake12", True, "env var API_KEY"),
        ("export TOKEN=abcdefghijklmnop", True, "export TOKEN assignment"),
        ("DEBUG = True", False, "benign config flag"),
        ('name = "not-a-secret-value"', False, "benign string assignment"),
    ],
)
def test_secret_pattern_detection(
    source_line: str,
    should_detect: bool,
    label: str,
) -> None:
    parser = RisksParser.__new__(RisksParser)
    detected = parser._line_has_secret(source_line)

    assert detected is should_detect, label


def test_secret_findings_in_critical_section() -> None:
    risks = RisksParser(str(FIXTURES_DIR)).parse()
    stack: StackResult = {
        "languages": [],
        "manifests": [],
        "frameworks": [],
        "dependencies": [],
        "is_empty": False,
    }
    git_log: GitLogResult = {
        "commits": [],
        "top_modified_files": [],
        "status_message": None,
    }
    generator = ReportGenerator(
        str(FIXTURES_DIR),
        stack,
        {},
        git_log,
        risks,
    )

    report = generator.generate()

    assert "### [CRITICAL]" in report
    for finding in EXPECTED_FINDINGS:
        assert (
            f"Hard-coded secret in {finding['file']}:{finding['line']}" in report
        )
