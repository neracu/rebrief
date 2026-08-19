from __future__ import annotations

import json
from pathlib import Path
from typing import Literal, TypedDict
from xml.etree import ElementTree as ET

from rebrief import __version__
from rebrief.core.badge import build_badge
from rebrief.core.confidence import Confidence, meets_threshold
from rebrief.core.diff import DiffScope, count_tracked_files
from rebrief.core.tokens import (
    TokenStats,
    complete_token_stats,
    count_tokens,
    empty_token_stats,
    format_savings_footnote,
)
from rebrief.core.vulnerabilities import VulnerabilityReport
from rebrief.parsers.freshness import DocDriftReport, empty_doc_drift_report
from rebrief.parsers.git_log import GitLogResult
from rebrief.parsers.manifests.versions import PackageSpec
from rebrief.parsers.ownership import (
    ModuleOwnership,
    OwnershipResult,
    format_ownership_table,
)
from rebrief.parsers.risks import RiskReport, is_test_or_fixture_path
from rebrief.parsers.rules import RuleFileEntry
from rebrief.parsers.stack import StackResult

Severity = Literal["critical", "warning", "info"]
ScanMode = Literal["full", "incremental"]


class ReportCommit(TypedDict):
    hash: str
    date: str
    message: str
    author: str


class ReportHotspot(TypedDict):
    file: str
    changes: int


class ReportSummary(TypedDict):
    languages_count: int
    risks_count: int
    ai_instruction_files: list[str]
    badge_url: str
    badge_markdown: str
    files_scanned: int
    files_total: int
    token_stats: TokenStats
    doc_drift: DocDriftReport


class ReportTechStack(TypedDict):
    languages: list[str]
    frameworks: list[str]
    manifests: list[str]
    dependencies: list[str]


class ReportTimeline(TypedDict):
    recent_commits: list[ReportCommit]
    hotspots: list[ReportHotspot]


class ReportRiskItem(TypedDict):
    message: str
    confidence: str


class ReportVulnerability(TypedDict):
    id: str
    package: str
    severity: str
    fixed_in: str
    summary: str


class ReportRiskMap(TypedDict):
    critical: list[ReportRiskItem]
    warning: list[ReportRiskItem]
    info: list[ReportRiskItem]
    vulnerabilities: list[ReportVulnerability]


class ReportPayload(TypedDict):
    version: str
    mode: ScanMode
    diff_ref: str | None
    summary: ReportSummary
    tech_stack: ReportTechStack
    timeline: ReportTimeline
    ownership_map: dict[str, ModuleOwnership]
    risk_map: ReportRiskMap
    checklist: list[str]


class _CollectedRiskItem(TypedDict):
    severity: Severity
    message: str
    confidence: str


def _xml_text(parent: ET.Element, tag: str, value: object) -> ET.Element:
    child = ET.SubElement(parent, tag)
    child.text = str(value)
    return child


def _xml_list(parent: ET.Element, wrapper: str, item_tag: str, values: list[str]) -> ET.Element:
    container = ET.SubElement(parent, wrapper)
    for value in values:
        _xml_text(container, item_tag, value)
    return container


class ReportGenerator:
    def __init__(
        self,
        repo_path: str,
        stack: StackResult,
        rules: dict[str, RuleFileEntry],
        git_log: GitLogResult,
        risks: RiskReport,
        min_confidence: Confidence = Confidence.MEDIUM,
        diff_scope: DiffScope | None = None,
        raw_token_stats: TokenStats | None = None,
        vulnerabilities: VulnerabilityReport | None = None,
        skip_vulnerability_check: bool = False,
        ownership: OwnershipResult | None = None,
        no_blame: bool = False,
        doc_drift: DocDriftReport | None = None,
    ) -> None:
        self._repo_path = Path(repo_path)
        self._stack = stack
        self._rules = rules
        self._git_log = git_log
        self._risks = risks
        self._min_confidence = min_confidence
        self._diff_scope = diff_scope
        self._raw_token_stats = raw_token_stats or empty_token_stats()
        self._token_stats: TokenStats | None = None
        self._vulnerabilities = vulnerabilities or {
            "findings": [],
            "skipped": False,
            "skip_message": None,
        }
        self._skip_vulnerability_check = skip_vulnerability_check
        self._ownership = ownership or {
            "modules": {},
            "skipped": no_blame,
            "skip_reason": "disabled via --no-blame" if no_blame else None,
        }
        self._no_blame = no_blame
        self._doc_drift = doc_drift or empty_doc_drift_report()

    @property
    def stack_packages(self) -> list[PackageSpec]:
        return list(self._stack["packages"])

    def generate(self) -> str:
        body = self._body()
        stats = self.token_stats()
        return body + "\n" + format_savings_footnote(stats) + "\n"

    def _body(self) -> str:
        sections = [
            self._title(),
            self._section_overview(),
            self._section_stack(),
            self._section_timeline(),
            self._section_risks(),
            self._section_doc_drift(),
            self._section_checklist(),
        ]
        return "\n\n".join(sections) + "\n"

    def token_stats(self) -> TokenStats:
        if self._token_stats is None:
            brief_tokens = count_tokens(self._body())
            raw = self._raw_token_stats
            self._token_stats = complete_token_stats(
                raw["raw_codebase_tokens"],
                brief_tokens,
                raw["tokenizer"],
            )
        return self._token_stats

    def generate_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False) + "\n"

    def generate_xml(self) -> str:
        payload = self.to_dict()
        root = ET.Element("rebrief", version=payload["version"])

        summary = ET.SubElement(root, "summary")
        stats = payload["summary"]["token_stats"]
        _xml_text(summary, "languages_count", payload["summary"]["languages_count"])
        _xml_text(summary, "risks_count", payload["summary"]["risks_count"])
        doc_drift = payload["summary"]["doc_drift"]
        _xml_text(summary, "freshness_score", doc_drift["freshness_score"])
        _xml_text(summary, "freshness_label", doc_drift["freshness_label"])
        drift_items = ET.SubElement(summary, "doc_drift_items")
        for item in doc_drift["items"]:
            drift = ET.SubElement(
                drift_items,
                "item",
                severity=item["severity"].upper(),
                confidence=item["confidence"],
                kind=item["kind"],
                source=item["source"],
            )
            drift.text = item["message"]
        _xml_text(summary, "raw_tokens", stats["raw_codebase_tokens"])
        _xml_text(summary, "brief_tokens", stats["brief_tokens"])
        _xml_text(summary, "savings_percentage", f"{stats['savings_percentage']:.2f}")

        tech_stack = ET.SubElement(root, "tech_stack")
        _xml_list(tech_stack, "languages", "language", payload["tech_stack"]["languages"])
        _xml_list(tech_stack, "frameworks", "framework", payload["tech_stack"]["frameworks"])
        _xml_list(tech_stack, "manifests", "manifest", payload["tech_stack"]["manifests"])

        hotspots = ET.SubElement(root, "hotspots")
        for entry in payload["timeline"]["hotspots"]:
            ET.SubElement(
                hotspots,
                "hotspot",
                file=entry["file"],
                changes=str(entry["changes"]),
            )

        ownership_map = ET.SubElement(root, "ownership_map")
        for module_path, entry in sorted(payload["ownership_map"].items()):
            module = ET.SubElement(
                ownership_map,
                "module",
                path=module_path,
                primary_owner=entry["primary_owner"],
                primary_percent=f"{entry['primary_percent']:.0f}",
                secondary=entry["secondary"],
                secondary_percent=f"{entry['secondary_percent']:.0f}",
                ai_assisted=str(entry["ai_assisted"]).lower(),
                ai_percent=f"{entry['ai_percent']:.1f}",
                expertise_level=entry["expertise_level"],
                rapid_ai_session=str(entry["rapid_ai_session"]).lower(),
                line_count=str(entry["line_count"]),
            )
            if entry["ai_tools"]:
                tools = ET.SubElement(module, "ai_tools")
                for tool in entry["ai_tools"]:
                    _xml_text(tools, "tool", tool)

        risk_map = ET.SubElement(root, "risk_map")
        for severity in ("critical", "warning", "info"):
            for item in payload["risk_map"][severity]:
                risk = ET.SubElement(
                    risk_map,
                    "risk",
                    severity=severity.upper(),
                    confidence=item["confidence"],
                )
                risk.text = item["message"]

        checklist = ET.SubElement(root, "checklist")
        for entry in payload["checklist"]:
            _xml_text(checklist, "item", entry)

        ET.indent(root, space="  ")
        body = ET.tostring(root, encoding="unicode")
        return '<?xml version="1.0" encoding="UTF-8"?>\n' + body + "\n"

    def write_report(self, output_path: str | Path = "REBRIEF.md") -> None:
        Path(output_path).write_text(self.generate(), encoding="utf-8")

    def write_json_report(self, output_path: str | Path = "REBRIEF.json") -> None:
        Path(output_path).write_text(self.generate_json(), encoding="utf-8")

    def write_xml_report(self, output_path: str | Path = "REBRIEF.xml") -> None:
        Path(output_path).write_text(self.generate_xml(), encoding="utf-8")

    def generate_html(self) -> str:
        from rebrief.formatters.html import render_html

        return render_html(self.to_dict(), self.generate(), self._repo_path.name)

    def write_html_report(self, output_path: str | Path = "REBRIEF.html") -> None:
        Path(output_path).write_text(self.generate_html(), encoding="utf-8")

    def filtered_risk_count(self) -> int:
        return len(self._filtered_risk_items())

    def _file_counts(self) -> tuple[int, int]:
        if self._diff_scope is not None:
            return self._diff_scope["files_scanned"], self._diff_scope["files_total"]
        total = count_tracked_files(self._repo_path)
        return total, total

    def to_dict(self) -> ReportPayload:
        risk_map = self._risk_map_payload()
        badge = build_badge(
            critical=len(risk_map["critical"]),
            warning=len(risk_map["warning"]),
            info=len(risk_map["info"]),
        )
        files_scanned, files_total = self._file_counts()
        return {
            "version": __version__,
            "mode": "incremental" if self._diff_scope is not None else "full",
            "diff_ref": self._diff_scope["ref"] if self._diff_scope is not None else None,
            "summary": {
                "languages_count": len(self._stack["languages"]),
                "risks_count": self.filtered_risk_count(),
                "ai_instruction_files": sorted(self._rules),
                "badge_url": badge["badge_url"],
                "badge_markdown": badge["badge_markdown"],
                "files_scanned": files_scanned,
                "files_total": files_total,
                "token_stats": self.token_stats(),
                "doc_drift": self._doc_drift,
            },
            "tech_stack": {
                "languages": list(self._stack["languages"]),
                "frameworks": list(self._stack["frameworks"]),
                "manifests": list(self._stack["manifests"]),
                "dependencies": list(self._stack["dependencies"]),
            },
            "timeline": {
                "recent_commits": [
                    {
                        "hash": commit["hash"],
                        "date": commit["date"],
                        "message": commit["subject"],
                        "author": commit["author"],
                    }
                    for commit in self._git_log["commits"]
                ],
                "hotspots": [
                    {
                        "file": entry["file"],
                        "changes": entry["count"],
                    }
                    for entry in self._git_log["top_modified_files"]
                ],
            },
            "ownership_map": dict(self._ownership["modules"]),
            "risk_map": risk_map,
            "checklist": self._checklist_items(),
        }

    def _collect_risk_items(self) -> list[_CollectedRiskItem]:
        items: list[_CollectedRiskItem] = []

        for entry in self._risks["secrets"]:
            if is_test_or_fixture_path(entry["file"]):
                items.append(
                    {
                        "severity": "warning",
                        "message": (
                            "Hard-coded secret-like value in test/example file "
                            f"{entry['file']}:{entry['line']}"
                        ),
                        "confidence": entry["confidence"],
                    }
                )
            else:
                items.append(
                    {
                        "severity": "critical",
                        "message": (
                            f"Hard-coded secret in {entry['file']}:{entry['line']}"
                        ),
                        "confidence": entry["confidence"],
                    }
                )

        if self._risks["missing_tests"]:
            items.append(
                {
                    "severity": "warning",
                    "message": "Missing tests directory (`tests/`, `test/`, or `__tests__/`).",
                    "confidence": Confidence.HIGH.value,
                }
            )

        for conflict in self._risks["dependency_conflicts"]:
            versions = ", ".join(conflict["versions"])
            items.append(
                {
                    "severity": "warning",
                    "message": (
                        f"Duplicate dependency `{conflict['package']}` "
                        f"with conflicting versions: {versions}."
                    ),
                    "confidence": Confidence.MEDIUM.value,
                }
            )

        for warning in self._stack["manifest_warnings"]:
            items.append(
                {
                    "severity": "warning",
                    "message": warning,
                    "confidence": Confidence.HIGH.value,
                }
            )

        for entry in self._risks["markers"]:
            items.append(
                {
                    "severity": "info",
                    "message": f"{entry['marker']} in {entry['file']}:{entry['line']}",
                    "confidence": entry["confidence"],
                }
            )

        if self._vulnerabilities["skipped"] and self._vulnerabilities["skip_message"]:
            items.append(
                {
                    "severity": "info",
                    "message": self._vulnerabilities["skip_message"],
                    "confidence": Confidence.HIGH.value,
                }
            )

        for finding in self._vulnerabilities["findings"]:
            fixed = finding["fixed_in"]
            fix_text = f" (fix: {fixed})" if fixed else ""
            items.append(
                {
                    "severity": finding["severity"],
                    "message": (
                        f"{finding['id']} in `{finding['package']}`: "
                        f"{finding['summary']}{fix_text}"
                    ),
                    "confidence": finding["confidence"],
                }
            )

        return items

    def _filtered_risk_items(self) -> list[_CollectedRiskItem]:
        return [
            item
            for item in self._collect_risk_items()
            if meets_threshold(Confidence(item["confidence"]), self._min_confidence)
        ]

    def _risk_map_payload(self) -> ReportRiskMap:
        critical: list[ReportRiskItem] = []
        warning: list[ReportRiskItem] = []
        info: list[ReportRiskItem] = []

        for item in self._filtered_risk_items():
            payload: ReportRiskItem = {
                "message": item["message"],
                "confidence": item["confidence"],
            }
            if item["severity"] == "critical":
                critical.append(payload)
            elif item["severity"] == "warning":
                warning.append(payload)
            else:
                info.append(payload)

        vulnerabilities = [
            {
                "id": finding["id"],
                "package": finding["package"],
                "severity": finding["severity"],
                "fixed_in": finding["fixed_in"],
                "summary": finding["summary"],
            }
            for finding in self._vulnerabilities["findings"]
        ]

        return {
            "critical": critical,
            "warning": warning,
            "info": info,
            "vulnerabilities": vulnerabilities,
        }

    def _title(self) -> str:
        if self._diff_scope is not None:
            return (
                f"# REBRIEF INCREMENTAL REPORT "
                f"(Diff against {self._diff_scope['ref']})"
            )
        name = self._repo_path.resolve().name or self._repo_path.name
        return f"# REBRIEF REPORT: {name}"

    def _section_overview(self) -> str:
        risk_count = self.filtered_risk_count()

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

        if self._diff_scope is not None:
            lines.append(
                f"- Files scanned in diff: {self._diff_scope['files_scanned']} / "
                f"Total files: {self._diff_scope['files_total']}."
            )

        if self._rules:
            lines.append(
                f"- Project context files found: {len(self._rules)} "
                f"({', '.join(sorted(self._rules))})."
            )
            for filename in sorted(self._rules):
                entry = self._rules[filename]
                lines.append(f"  - `{filename}`: {entry['lines_count']} lines")
        else:
            lines.append("- Project context files found: none.")

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

        lines.append("")
        lines.extend(self._section_ownership())

        return "\n".join(lines)

    def _section_ownership(self) -> list[str]:
        lines = ["### 👥 Code Ownership & Expertise Map"]

        if self._no_blame or self._ownership.get("skipped"):
            lines.append(
                "- Git blame ownership analysis skipped (`--no-blame`)."
            )
            return lines

        modules = self._ownership.get("modules", {})
        if not modules:
            if self._git_log.get("status_message"):
                return []
            lines.append("- None detected.")
            return lines

        lines.extend(format_ownership_table(modules))
        return lines

    def _section_risks(self) -> str:
        lines = [
            "## 4. Risk Map (AI Debt & Security)",
            "### [CRITICAL]",
        ]
        lines.extend(self._format_risk_tier("critical"))
        lines.append("")
        lines.append("### [WARNING]")
        lines.extend(self._format_risk_tier("warning"))
        lines.append("")
        lines.append("### [INFO]")
        lines.extend(self._format_risk_tier("info"))
        if not self._skip_vulnerability_check:
            lines.append("")
            lines.extend(self._section_vulnerability_report())
        return "\n".join(lines)

    def _section_vulnerability_report(self) -> list[str]:
        lines = ["### 🛡️ Vulnerability Report"]
        findings = self._vulnerabilities["findings"]
        if not findings:
            lines.append("- None detected.")
            return lines

        for finding in findings:
            fixed = finding["fixed_in"]
            fix_text = f" — upgrade to `{fixed}`" if fixed else ""
            lines.append(
                f"- **{finding['id']}** (`{finding['package']}`): "
                f"{finding['summary']}{fix_text}"
            )
        return lines

    def _format_risk_tier(self, severity: Severity) -> list[str]:
        items = [
            item for item in self._filtered_risk_items() if item["severity"] == severity
        ]
        if not items:
            return ["- None detected."]
        return [self._format_risk_line(item) for item in items]

    def _format_risk_line(self, item: _CollectedRiskItem) -> str:
        severity_label = item["severity"].upper()
        confidence_label = item["confidence"]
        message = item["message"]
        if item["confidence"] == Confidence.LOW.value:
            message = f"{message} (Requires Verification)"
        return (
            f"- [{severity_label}] [Confidence: {confidence_label}] {message}"
        )

    def _is_filtered_risk(self, confidence_value: str) -> bool:
        return meets_threshold(Confidence(confidence_value), self._min_confidence)

    def _checklist_items(self) -> list[str]:
        items: list[str] = []

        for secret in self._risks["secrets"]:
            if not self._is_filtered_risk(secret["confidence"]):
                continue
            if is_test_or_fixture_path(secret["file"]):
                items.append(
                    "Confirm the secret-like value in "
                    f"{secret['file']} (line {secret['line']}) "
                    "is a test fixture, not a live credential."
                )
            else:
                items.append(
                    "Review and rotate hard-coded credentials in "
                    f"{secret['file']} (line {secret['line']})."
                )

        if self._risks["missing_tests"] and self._is_filtered_risk(Confidence.HIGH.value):
            items.append("Add a `tests/` directory and cover critical paths.")

        for conflict in self._risks["dependency_conflicts"]:
            if not self._is_filtered_risk(Confidence.MEDIUM.value):
                continue
            versions = ", ".join(conflict["versions"])
            items.append(
                f"Resolve version conflict for `{conflict['package']}`: {versions}."
            )

        for finding in self._vulnerabilities["findings"]:
            if not self._is_filtered_risk(finding["confidence"]):
                continue
            if finding["fixed_in"]:
                items.append(
                    f"Upgrade `{finding['package']}` to {finding['fixed_in']} "
                    f"({finding['id']})."
                )

        for framework in self._stack["frameworks"]:
            items.append(f"Set up the development environment for {framework}.")

        for entry in self._git_log["top_modified_files"]:
            if self._diff_scope is not None:
                items.append(
                    "Review changed file in diff: "
                    f"{entry['file']} ({entry['count']} line changes)."
                )
            else:
                items.append(
                    "Review frequently changed file: "
                    f"{entry['file']} ({entry['count']} edits in 30 days)."
                )

        for item in self._doc_drift["items"]:
            if item["severity"] != "warning":
                continue
            items.append(f"Update documentation: {item['message']}")

        if not items:
            items.append("Review the sections above and validate the project setup.")

        return items

    def _section_doc_drift(self) -> str:
        drift = self._doc_drift
        lines = [
            "## 6. 📉 Documentation Freshness & Drift",
            (
                f"Freshness Score: {drift['freshness_score']}% "
                f"({drift['freshness_label']})"
            ),
        ]
        if drift["items"]:
            for item in drift["items"]:
                severity_label = item["severity"].upper()
                lines.append(
                    f"- [{severity_label}] [Confidence: {item['confidence']}] "
                    f"{item['message']}"
                )
        else:
            lines.append("- No documentation drift detected.")
        return "\n".join(lines)

    def _section_checklist(self) -> str:
        lines = ['## 7. Developer Checklist ("Where to Start")']
        lines.extend(
            f"{index}. {item}" for index, item in enumerate(self._checklist_items(), start=1)
        )
        return "\n".join(lines)
