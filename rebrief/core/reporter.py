from __future__ import annotations

from pathlib import Path

from rebrief.parsers.git_log import GitLogResult
from rebrief.parsers.risks import RiskReport
from rebrief.parsers.rules import RuleFileEntry
from rebrief.parsers.stack import StackResult


class ReportGenerator:
    def __init__(
        self,
        repo_path: str,
        stack: StackResult,
        rules: dict[str, RuleFileEntry],
        git_log: GitLogResult,
        risks: RiskReport,
    ) -> None:
        self._repo_path = Path(repo_path)
        self._stack = stack
        self._rules = rules
        self._git_log = git_log
        self._risks = risks

    def generate(self) -> str:
        sections = [
            self._title(),
            self._section_overview(),
            self._section_stack(),
            self._section_timeline(),
            self._section_risks(),
            self._section_checklist(),
        ]
        return "\n\n".join(sections) + "\n"

    def write_report(self, output_path: str | Path = "REBRIEF.md") -> None:
        Path(output_path).write_text(self.generate(), encoding="utf-8")

    def _title(self) -> str:
        return f"# REBRIEF REPORT: {self._repo_path.name}"

    def _section_overview(self) -> str:
        ai_files = [
            filename
            for filename in self._rules
            if filename != "README.md"
        ]
        risk_count = (
            len(self._risks["secrets"])
            + (1 if self._risks["missing_tests"] else 0)
            + len(self._risks["dependency_conflicts"])
            + len(self._risks["markers"])
        )

        if self._stack["is_empty"]:
            impression = "Empty repository detected."
        elif risk_count == 0:
            impression = (
                f"This repository appears well-structured with "
                f"{len(self._stack['languages'])} detected language(s) "
                f"and no major risks flagged."
            )
        else:
            impression = (
                f"This repository uses {len(self._stack['languages'])} language(s) "
                f"and has {risk_count} risk item(s) that need developer attention."
            )

        lines = [
            "## 1. Project Overview (Executive Summary)",
            f"- {impression}",
        ]

        if self._rules:
            lines.append(
                f"- AI instruction files found: {len(self._rules)} "
                f"({', '.join(sorted(self._rules))})."
            )
            for filename in sorted(self._rules):
                entry = self._rules[filename]
                lines.append(f"  - `{filename}`: {entry['lines_count']} lines")
        else:
            lines.append("- AI instruction files found: none.")

        return "\n".join(lines)

    def _section_stack(self) -> str:
        lines = [
            "## 2. Technology Stack and Dependencies",
            "- **Languages:** "
            + (", ".join(self._stack["languages"]) or "None detected"),
            "- **Frameworks:** "
            + (", ".join(self._stack["frameworks"]) or "None detected"),
            "- **Manifests:** "
            + (", ".join(self._stack["manifests"]) or "None detected"),
            "- **Key dependencies:**",
        ]

        if self._stack["dependencies"]:
            lines.extend(f"  - `{dependency}`" for dependency in self._stack["dependencies"])
        else:
            lines.append("  - None detected")

        return "\n".join(lines)

    def _section_timeline(self) -> str:
        lines = ["## 3. Solution Timeline (Git History)"]

        if self._git_log["commits"]:
            for commit in self._git_log["commits"]:
                lines.append(
                    f"- `{commit['hash']}` ({commit['date']}) "
                    f"{commit['subject']} — {commit['author']}"
                )
        elif self._git_log.get("status_message"):
            lines.append(f"- {self._git_log['status_message']}")
        else:
            lines.append("- No meaningful commits found.")

        lines.append("")
        lines.append("### Hotspots (Change Density)")

        if self._git_log["top_modified_files"]:
            for entry in self._git_log["top_modified_files"]:
                lines.append(f"- {entry['file']}: {entry['count']} changes")
        else:
            lines.append("- None detected.")

        return "\n".join(lines)

    def _section_risks(self) -> str:
        lines = [
            "## 4. Risk Map (AI Debt & Security)",
            "### [CRITICAL]",
        ]
        lines.extend(self._format_critical_risks())
        lines.append("")
        lines.append("### [WARNING]")
        lines.extend(self._format_warning_risks())
        lines.append("")
        lines.append("### [INFO]")
        lines.extend(self._format_info_risks())
        return "\n".join(lines)

    def _format_critical_risks(self) -> list[str]:
        if not self._risks["secrets"]:
            return ["- None detected."]

        return [
            f"- Hard-coded secret in {entry['file']}:{entry['line']}"
            for entry in self._risks["secrets"]
        ]

    def _format_warning_risks(self) -> list[str]:
        warnings: list[str] = []

        if self._risks["missing_tests"]:
            warnings.append("- Missing tests directory (`tests/`, `test/`, or `__tests__/`).")

        for conflict in self._risks["dependency_conflicts"]:
            versions = ", ".join(conflict["versions"])
            warnings.append(
                f"- Duplicate dependency `{conflict['package']}` "
                f"with conflicting versions: {versions}."
            )

        return warnings or ["- None detected."]

    def _format_info_risks(self) -> list[str]:
        if not self._risks["markers"]:
            return ["- None detected."]

        return [
            f"- {entry['marker']} in {entry['file']}:{entry['line']}"
            for entry in self._risks["markers"]
        ]

    def _section_checklist(self) -> str:
        items: list[str] = []

        for secret in self._risks["secrets"]:
            items.append(
                "Review and rotate hard-coded credentials in "
                f"{secret['file']} (line {secret['line']})."
            )

        if self._risks["missing_tests"]:
            items.append("Add a `tests/` directory and cover critical paths.")

        for conflict in self._risks["dependency_conflicts"]:
            versions = ", ".join(conflict["versions"])
            items.append(
                f"Resolve version conflict for `{conflict['package']}`: {versions}."
            )

        for framework in self._stack["frameworks"]:
            items.append(f"Set up the development environment for {framework}.")

        for entry in self._git_log["top_modified_files"]:
            items.append(
                "Review frequently changed file: "
                f"{entry['file']} ({entry['count']} edits in 30 days)."
            )

        if not items:
            items.append("Review the sections above and validate the project setup.")

        lines = ['## 5. Developer Checklist ("Where to Start")']
        lines.extend(f"{index}. {item}" for index, item in enumerate(items, start=1))
        return "\n".join(lines)
