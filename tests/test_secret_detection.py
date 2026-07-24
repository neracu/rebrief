from pathlib import Path

import pytest

from rebrief.core.reporter import ReportGenerator
from rebrief.parsers.git_log import GitLogResult
from rebrief.parsers.risks import RisksParser
from rebrief.parsers.stack import StackResult

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "secrets"
DEFAULT_RELATIVE_PATH = "app/config.py"

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
    ("source_line", "relative_path", "should_detect", "label"),
    [
        (
            'api_key = "aB3xQ9mK7pL2wZ8vN4tR"',
            DEFAULT_RELATIVE_PATH,
            True,
            "quoted api_key assignment with 20+ char value",
        ),
        (
            'api_key = "abcdefghijklmnop"',
            DEFAULT_RELATIVE_PATH,
            False,
            "16-char value below entropy-path minimum",
        ),
        (
            'password = "admin12345"',
            DEFAULT_RELATIVE_PATH,
            False,
            "short password below entropy-path minimum",
        ),
        (
            'password = "Tr7mK9qX2wZ8Lp4Yv6Bn3"',
            DEFAULT_RELATIVE_PATH,
            True,
            "long high-entropy generic password",
        ),
        (
            'ACCESS_KEY = "AKIAIOSFODNN7EXAMPLE"',
            DEFAULT_RELATIVE_PATH,
            True,
            "AWS access key ID",
        ),
        (
            'client_key = "sk-proj-fakefakefakefakefakefake12"',
            DEFAULT_RELATIVE_PATH,
            True,
            "OpenAI-style sk- key",
        ),
        (
            "API_KEY=sk-fakefakefakefakefakefake12",
            "config/api_keys.cfg",
            True,
            "env var API_KEY",
        ),
        (
            "export TOKEN=aB3xQ9mK7pL2wZ8vN4tR",
            "config/env.sh",
            True,
            "export TOKEN assignment with 20+ char value",
        ),
        ("DEBUG = True", DEFAULT_RELATIVE_PATH, False, "benign config flag"),
        (
            'name = "not-a-secret-value"',
            DEFAULT_RELATIVE_PATH,
            False,
            "benign string assignment without credential name",
        ),
        (
            'foreign_keys="[GraphEdge.source_id]"',
            DEFAULT_RELATIVE_PATH,
            False,
            "ORM-style bracketed field reference, not a secret",
        ),
        (
            "CacheKey = tuple[str | uuid.UUID, ...]",
            DEFAULT_RELATIVE_PATH,
            False,
            "type alias/subscript expression, not a string literal",
        ),
        (
            'api_key = (settings.llm_api_key or "").strip()',
            DEFAULT_RELATIVE_PATH,
            False,
            "settings reference with boolean fallback, not a literal",
        ),
        (
            'className="flex items-center gap-2 rounded-lg border p-4"',
            "components/card.tsx",
            False,
            "Tailwind className string excluded by context",
        ),
        (
            'd="M12.5 3.5L2 21h21L12.5 3.5z"',
            "components/icons/icon.tsx",
            False,
            "SVG path d attribute excluded by context",
        ),
        (
            'revision = "a3f8e91b2c4d9e7f1234"',
            "apps/backend/alembic/versions/0001_create_users.py",
            False,
            "Alembic revision hash excluded in migration path",
        ),
        (
            'revision = "a3f8e91b2c4d9e7f1234"',
            "app/models.py",
            False,
            "revision field outside migration path is not a credential name",
        ),
        (
            'STORAGE_KEY = "vast:last-project:v2"',
            "src/lib/storage.ts",
            False,
            "namespaced localStorage key with version suffix",
        ),
        (
            'STORAGE_KEY = "vast:pinned-projects:v1"',
            "src/lib/storage.ts",
            False,
            "namespaced localStorage key for pinned projects",
        ),
        (
            'const STORAGE_KEY = "vast:last-project:v2"',
            "src/lib/storage.ts",
            False,
            "const-prefixed namespaced storage key",
        ),
    ],
)
def test_secret_pattern_detection(
    source_line: str,
    relative_path: str,
    should_detect: bool,
    label: str,
) -> None:
    parser = RisksParser.__new__(RisksParser)
    detected = parser._line_has_secret(source_line, relative_path)

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
