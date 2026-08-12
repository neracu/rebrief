from __future__ import annotations

from pathlib import Path

from rebrief.ci.comment import (
    COMMENT_MARKER,
    build_pr_comment,
    has_warning_or_critical_risks,
    section_has_findings,
)

SAMPLE_REPORT_WITH_RISKS = """\
# REBRIEF REPORT: my-app

## 1. Project Overview (Executive Summary)
- This repository uses 1 language(s) and has 4 risk item(s) that need developer attention.
- Project context files found: 2 (.cursorrules, CLAUDE.md).

## 2. Technology Stack and Dependencies
- **Languages:** Python
- **Frameworks:** Django
- **Manifests:** pyproject.toml

## 3. Solution Timeline (Git History)
- `a1b2c3d` (2026-01-15) Add authentication module — Alice

### Hotspots (Change Density)
- src/app.py: 8 changes

## 4. Risk Map (AI Debt & Security)
### [CRITICAL]
- Hard-coded secret in config.py:3

### [WARNING]
- Missing tests directory (`tests/`, `test/`, or `__tests__/`).

### [INFO]
- TODO in app.py:10

## 5. Developer Checklist ("Where to Start")
1. Review and rotate hard-coded credentials in config.py (line 3).
2. Add a `tests/` directory and cover critical paths.
"""

SAMPLE_REPORT_NO_RISKS = """\
# REBRIEF REPORT: clean-app

## 1. Project Overview (Executive Summary)
- This repository appears well-structured with 1 detected language(s) and no major risks flagged.

## 2. Technology Stack and Dependencies
- **Languages:** Python

## 3. Solution Timeline (Git History)
- None detected.

### Hotspots (Change Density)
- None detected.

## 4. Risk Map (AI Debt & Security)
### [CRITICAL]
- None detected.

### [WARNING]
- None detected.

### [INFO]
- None detected.

## 5. Developer Checklist ("Where to Start")
1. Review the sections above and validate the project setup.
"""


def test_section_has_findings_true():
    assert section_has_findings(["- Hard-coded secret in config.py:3"]) is True


def test_section_has_findings_false():
    assert section_has_findings(["- None detected."]) is False


def test_has_warning_or_critical_risks_when_findings_present():
    assert has_warning_or_critical_risks(SAMPLE_REPORT_WITH_RISKS) is True


def test_has_warning_or_critical_risks_when_none_detected():
    assert has_warning_or_critical_risks(SAMPLE_REPORT_NO_RISKS) is False


def test_has_warning_or_critical_risks_ignores_info_only():
    report = SAMPLE_REPORT_NO_RISKS.replace(
        "### [INFO]\n- None detected.",
        "### [INFO]\n- TODO in app.py:10",
    )
    assert has_warning_or_critical_risks(report) is False


def test_build_pr_comment_includes_marker_and_key_sections():
    comment, truncated = build_pr_comment(
        SAMPLE_REPORT_WITH_RISKS,
        commit_sha="abc1234",
        run_url="https://github.com/example/run/1",
        timestamp="2026-01-15T12:00:00Z",
    )

    assert truncated is False
    assert comment.startswith(COMMENT_MARKER)
    assert "## rebrief scan report" in comment
    assert "## 1. Project Overview" in comment
    assert "## 4. Risk Map" in comment
    assert '## 5. Developer Checklist ("Where to Start")' in comment
    assert "Hard-coded secret in config.py:3" in comment
    assert "<details>" in comment
    assert "Technology Stack & Git Timeline" in comment
    assert "pypi.org/project/rebrief" in comment
    assert "abc1234" in comment
    assert "workflow run" in comment


def test_build_pr_comment_truncates_when_too_long():
    huge_report = SAMPLE_REPORT_WITH_RISKS + ("\n- filler line" * 10_000)
    comment, truncated = build_pr_comment(huge_report, max_length=2_000)

    assert truncated is True
    assert len(comment) <= 2_000
    assert "Report truncated" in comment


def test_cli_build_writes_output(tmp_path: Path):
    report_path = tmp_path / "REBRIEF.md"
    report_path.write_text(SAMPLE_REPORT_WITH_RISKS, encoding="utf-8")
    output_path = tmp_path / "comment.md"

    from rebrief.ci.comment import main

    exit_code = main(
        [
            "build",
            "--report-path",
            str(report_path),
            "--output",
            str(output_path),
            "--commit-sha",
            "deadbeef",
        ]
    )

    assert exit_code == 0
    body = output_path.read_text(encoding="utf-8")
    assert body.startswith(COMMENT_MARKER)
    assert "deadbee" in body


def test_cli_has_risks_exit_codes(tmp_path: Path):
    from rebrief.ci.comment import main

    report_path = tmp_path / "REBRIEF.md"
    output_path = tmp_path / "has-risks.txt"

    report_path.write_text(SAMPLE_REPORT_WITH_RISKS, encoding="utf-8")
    assert (
        main(
            [
                "has-risks",
                "--report-path",
                str(report_path),
                "--output",
                str(output_path),
            ]
        )
        == 0
    )
    assert output_path.read_text(encoding="utf-8") == "true"

    report_path.write_text(SAMPLE_REPORT_NO_RISKS, encoding="utf-8")
    assert main(["has-risks", "--report-path", str(report_path)]) == 2
