from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, TypedDict
from xml.etree import ElementTree as ET

from rebrief import __version__
from rebrief.core.reporter import ReportGenerator, ReportPayload, ReportRiskItem
from rebrief.core.tokens import (
    TokenStats,
    complete_token_stats,
    count_tokens,
    empty_token_stats,
    format_savings_footnote,
)
from rebrief.parsers.manifests.versions import PackageSpec


def _xml_text(parent: ET.Element, tag: str, value: object) -> ET.Element:
    child = ET.SubElement(parent, tag)
    child.text = str(value)
    return child

FRONTEND_FRAMEWORKS: frozenset[str] = frozenset(
    {
        "Next.js",
        "React",
        "Vue",
        "Angular",
        "Svelte",
        "Nuxt.js",
        "Remix",
        "Vite",
    }
)

BACKEND_FRAMEWORKS: frozenset[str] = frozenset(
    {
        "FastAPI",
        "Django",
        "Django REST Framework",
        "Flask",
        "Express",
        "NestJS",
        "Gin",
        "Echo",
        "Fiber",
        "Spring Boot",
        "Quarkus",
        "Micronaut",
        "Rails",
        "Laravel",
        "Symfony",
        "Slim",
        "Sinatra",
        "Actix Web",
        "Axum",
        "Rocket",
    }
)

INFRA_FILENAMES: dict[str, str] = {
    "Dockerfile": "Docker",
    "docker-compose.yml": "Docker Compose",
    "docker-compose.yaml": "Docker Compose",
    "Chart.yaml": "Helm",
}

INFRA_SUFFIXES: tuple[tuple[str, str], ...] = (
    (".tf", "Terraform"),
    (".tfvars", "Terraform"),
)


class ArchitectureTier(TypedDict):
    role: str
    service: str
    frameworks: list[str]


class HotspotEntry(TypedDict):
    rank: int
    service: str
    file: str
    changes: int


class DependencyOccurrence(TypedDict):
    service: str
    version: str


class SharedDependency(TypedDict):
    ecosystem: str
    package: str
    occurrences: list[DependencyOccurrence]
    kind: Literal["duplicate", "mismatch"]


class SystemSummary(TypedDict):
    services_count: int
    risks_count: int
    token_stats: TokenStats


class SystemReportPayload(TypedDict):
    version: str
    kind: Literal["system"]
    summary: SystemSummary
    architecture: list[ArchitectureTier]
    architecture_line: str
    hotspot_matrix: list[HotspotEntry]
    risk_map: dict[str, list[ReportRiskItem]]
    shared_dependencies: list[SharedDependency]
    checklist: list[str]
    services: list[ReportPayload]


@dataclass(frozen=True)
class ScannedService:
    name: str
    source: str
    generator: ReportGenerator


def detect_infra_signals(member_path: str | Path) -> list[str]:
    root = Path(member_path)
    if not root.is_dir():
        return []

    signals: set[str] = set()
    max_depth = 3

    for dir_root, dirs, files in os.walk(root):
        dir_path = Path(dir_root)
        depth = len(dir_path.relative_to(root).parts)
        if depth > max_depth:
            dirs[:] = []
            continue

        dirs[:] = [
            directory
            for directory in sorted(dirs)
            if directory != "node_modules" and not directory.startswith(".")
        ]

        for filename in files:
            label = INFRA_FILENAMES.get(filename)
            if label is not None:
                signals.add(label)
                continue
            for suffix, infra_label in INFRA_SUFFIXES:
                if filename.endswith(suffix):
                    signals.add(infra_label)

    return sorted(signals)


def classify_service_tier(
    frameworks: list[str],
    infra_signals: list[str],
) -> str:
    frontend = [fw for fw in frameworks if fw in FRONTEND_FRAMEWORKS]
    backend = [fw for fw in frameworks if fw in BACKEND_FRAMEWORKS]

    if frontend and not backend and not infra_signals:
        return "Frontend"
    if backend and not frontend and not infra_signals:
        return "Backend"
    if infra_signals and not frontend and not backend:
        return "Infra"
    if frontend:
        return "Frontend"
    if backend:
        return "Backend"
    if infra_signals:
        return "Infra"
    return "Shared"


def build_architecture_tiers(services: list[ScannedService]) -> list[ArchitectureTier]:
    tiers: list[ArchitectureTier] = []
    for service in services:
        payload = service.generator.to_dict()
        frameworks = list(payload["tech_stack"]["frameworks"])
        infra = detect_infra_signals(service.generator._repo_path)
        display_frameworks = frameworks or infra or ["(no stack detected)"]
        tiers.append(
            {
                "role": classify_service_tier(frameworks, infra),
                "service": service.name,
                "frameworks": display_frameworks,
            }
        )
    return tiers


def format_architecture_line(tiers: list[ArchitectureTier]) -> str:
    grouped: dict[str, list[str]] = {}
    for tier in tiers:
        role = tier["role"]
        label = ", ".join(tier["frameworks"])
        grouped.setdefault(role, []).append(f"{label} ({tier['service']})")

    parts: list[str] = []
    for role in ("Frontend", "Backend", "Infra", "Shared"):
        if role not in grouped:
            continue
        parts.append(f"{role}: {' | '.join(grouped[role])}")
    return " | ".join(parts) if parts else "No architecture signals detected"


def build_hotspot_matrix(services: list[ScannedService]) -> list[HotspotEntry]:
    rows: list[tuple[int, str, str, int]] = []
    for service in services:
        payload = service.generator.to_dict()
        for hotspot in payload["timeline"]["hotspots"]:
            rows.append(
                (
                    hotspot["changes"],
                    service.name,
                    hotspot["file"],
                    hotspot["changes"],
                )
            )

    rows.sort(key=lambda item: (-item[0], item[1], item[2]))
    return [
        {
            "rank": index,
            "service": service,
            "file": file_path,
            "changes": changes,
        }
        for index, (_, service, file_path, changes) in enumerate(rows, start=1)
    ]


def build_shared_dependencies(services: list[ScannedService]) -> list[SharedDependency]:
    grouped: dict[tuple[str, str], list[DependencyOccurrence]] = {}

    for service in services:
        for package in service.generator.stack_packages:
            key = (package["ecosystem"], package["name"])
            grouped.setdefault(key, []).append(
                {
                    "service": service.name,
                    "version": package["version"],
                }
            )

    results: list[SharedDependency] = []
    for (ecosystem, name), occurrences in sorted(grouped.items()):
        if len(occurrences) < 2:
            continue
        versions = {item["version"] for item in occurrences}
        kind: Literal["duplicate", "mismatch"] = (
            "mismatch" if len(versions) > 1 else "duplicate"
        )
        results.append(
            {
                "ecosystem": ecosystem,
                "package": name,
                "occurrences": occurrences,
                "kind": kind,
            }
        )

    mismatch_first = sorted(
        results,
        key=lambda item: (0 if item["kind"] == "mismatch" else 1, item["package"]),
    )
    return mismatch_first


def _prefix_message(service: str, message: str) -> str:
    return f"[{service}] {message}"


def build_unified_risk_map(
    services: list[ScannedService],
) -> dict[str, list[ReportRiskItem]]:
    unified: dict[str, list[ReportRiskItem]] = {
        "critical": [],
        "warning": [],
        "info": [],
        "vulnerabilities": [],
    }

    for service in services:
        risk_map = service.generator.to_dict()["risk_map"]
        for severity in ("critical", "warning", "info"):
            for item in risk_map[severity]:
                unified[severity].append(
                    {
                        "message": _prefix_message(service.name, item["message"]),
                        "confidence": item["confidence"],
                    }
                )
        for finding in risk_map["vulnerabilities"]:
            fixed = finding.get("fixed_in") or ""
            fix_text = f" (fix: {fixed})" if fixed else ""
            message = (
                f"{finding['id']} in `{finding['package']}`: "
                f"{finding['summary']}{fix_text}"
            )
            unified["vulnerabilities"].append(
                {
                    "message": _prefix_message(service.name, message),
                    "confidence": "HIGH",
                }
            )

    return unified


def build_unified_checklist(services: list[ScannedService]) -> list[str]:
    items: list[str] = []
    for service in services:
        for entry in service.generator.to_dict()["checklist"]:
            items.append(_prefix_message(service.name, entry))
    if not items:
        items.append("Review the system sections above and validate each service setup.")
    return items


class SystemReportGenerator:
    def __init__(self, services: list[ScannedService]) -> None:
        self._services = services
        self._architecture = build_architecture_tiers(services)
        self._architecture_line = format_architecture_line(self._architecture)
        self._hotspots = build_hotspot_matrix(services)
        self._risk_map = build_unified_risk_map(services)
        self._shared_dependencies = build_shared_dependencies(services)
        self._checklist = build_unified_checklist(services)
        self._token_stats: TokenStats | None = None

    def _body(self) -> str:
        sections = [
            self._title(),
            self._section_overview(),
            self._section_architecture(),
            self._section_hotspots(),
            self._section_risks(),
            self._section_shared_dependencies(),
            self._section_checklist(),
            self._section_services(),
        ]
        return "\n\n".join(sections) + "\n"

    def token_stats(self) -> TokenStats:
        if self._token_stats is None:
            raw_total = sum(
                service.generator.to_dict()["summary"]["token_stats"]["raw_codebase_tokens"]
                for service in self._services
            )
            brief_tokens = count_tokens(self._body())
            tokenizer = (
                self._services[0].generator.to_dict()["summary"]["token_stats"]["tokenizer"]
                if self._services
                else empty_token_stats()["tokenizer"]
            )
            self._token_stats = complete_token_stats(raw_total, brief_tokens, tokenizer)
        return self._token_stats

    def generate(self) -> str:
        body = self._body()
        return body + "\n" + format_savings_footnote(self.token_stats()) + "\n"

    def generate_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False) + "\n"

    def generate_xml(self) -> str:
        payload = self.to_dict()
        root = ET.Element("rebrief-system", version=payload["version"])

        summary = ET.SubElement(root, "summary")
        stats = payload["summary"]["token_stats"]
        _xml_text(summary, "services_count", payload["summary"]["services_count"])
        _xml_text(summary, "risks_count", payload["summary"]["risks_count"])
        _xml_text(summary, "raw_tokens", stats["raw_codebase_tokens"])
        _xml_text(summary, "brief_tokens", stats["brief_tokens"])
        _xml_text(summary, "savings_percentage", f"{stats['savings_percentage']:.2f}")

        architecture = ET.SubElement(root, "architecture")
        _xml_text(architecture, "line", payload["architecture_line"])

        hotspots = ET.SubElement(root, "hotspots")
        for entry in payload["hotspot_matrix"][:20]:
            ET.SubElement(
                hotspots,
                "hotspot",
                rank=str(entry["rank"]),
                service=entry["service"],
                file=entry["file"],
                changes=str(entry["changes"]),
            )

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

    def write_report(self, output_path: str | Path) -> None:
        Path(output_path).write_text(self.generate(), encoding="utf-8")

    def write_json_report(self, output_path: str | Path) -> None:
        Path(output_path).write_text(self.generate_json(), encoding="utf-8")

    def write_xml_report(self, output_path: str | Path) -> None:
        Path(output_path).write_text(self.generate_xml(), encoding="utf-8")

    def _risk_count(self) -> int:
        return sum(
            len(items)
            for severity, items in self._risk_map.items()
            if severity != "vulnerabilities"
        )

    def to_dict(self) -> SystemReportPayload:
        risk_count = self._risk_count()
        return {
            "version": __version__,
            "kind": "system",
            "summary": {
                "services_count": len(self._services),
                "risks_count": risk_count,
                "token_stats": self.token_stats(),
            },
            "architecture": self._architecture,
            "architecture_line": self._architecture_line,
            "hotspot_matrix": self._hotspots,
            "risk_map": self._risk_map,
            "shared_dependencies": self._shared_dependencies,
            "checklist": self._checklist,
            "services": [service.generator.to_dict() for service in self._services],
        }

    def _title(self) -> str:
        return "# REBRIEF SYSTEM REPORT"

    def _section_overview(self) -> str:
        risk_count = self._risk_count()
        lines = [
            "## 1. System Overview",
            f"- Services scanned: {len(self._services)}",
            f"- Unified risk items: {risk_count}",
            f"- Architecture: {self._architecture_line}",
        ]
        return "\n".join(lines)

    def _section_architecture(self) -> str:
        lines = ["## 2. System Architecture Summary"]
        for tier in self._architecture:
            frameworks = ", ".join(tier["frameworks"])
            lines.append(
                f"- **{tier['role']}** (`{tier['service']}`): {frameworks}"
            )
        return "\n".join(lines)

    def _section_hotspots(self) -> str:
        lines = ["## 3. Cross-Repo Hotspot Matrix"]
        if not self._hotspots:
            lines.append("- None detected.")
            return "\n".join(lines)

        lines.append("")
        lines.append("| Rank | Service | File | Changes |")
        lines.append("| --- | --- | --- | ---: |")
        for entry in self._hotspots[:25]:
            lines.append(
                f"| {entry['rank']} | `{entry['service']}` | `{entry['file']}` | {entry['changes']} |"
            )
        return "\n".join(lines)

    def _section_risks(self) -> str:
        lines = ["## 4. Unified Risk Map"]
        for severity, label in (
            ("critical", "CRITICAL"),
            ("warning", "WARNING"),
            ("info", "INFO"),
        ):
            lines.append(f"### [{label}]")
            items = self._risk_map[severity]
            if not items:
                lines.append("- None detected.")
            else:
                for item in items:
                    lines.append(
                        f"- [{label}] [Confidence: {item['confidence']}] {item['message']}"
                    )
            lines.append("")

        lines.append("### Vulnerabilities")
        vulns = self._risk_map["vulnerabilities"]
        if not vulns:
            lines.append("- None detected.")
        else:
            for item in vulns:
                lines.append(f"- {item['message']}")
        return "\n".join(lines).rstrip()

    def _section_shared_dependencies(self) -> str:
        lines = ["## 5. Shared Dependency Graph"]
        if not self._shared_dependencies:
            lines.append("- No duplicated dependencies across services.")
            return "\n".join(lines)

        for entry in self._shared_dependencies:
            kind_label = "Mismatch" if entry["kind"] == "mismatch" else "Duplicate"
            versions = ", ".join(
                f"`{occurrence['service']}`@{occurrence['version']}"
                for occurrence in entry["occurrences"]
            )
            lines.append(
                f"- **[{kind_label}]** `{entry['package']}` ({entry['ecosystem']}): {versions}"
            )
        return "\n".join(lines)

    def _section_checklist(self) -> str:
        lines = ['## 6. Developer Checklist ("Where to Start")']
        lines.extend(
            f"{index}. {item}" for index, item in enumerate(self._checklist, start=1)
        )
        return "\n".join(lines)

    def _section_services(self) -> str:
        sections: list[str] = ["## 7. Per-Service Summaries"]
        for service in self._services:
            payload = service.generator.to_dict()
            stack = payload["tech_stack"]
            sections.append("---")
            sections.append(f"## Service: {service.name}")
            sections.append(f"- Source: `{service.source}`")
            sections.append(
                "- **Languages:** " + (", ".join(stack["languages"]) or "None detected")
            )
            sections.append(
                "- **Frameworks:** "
                + (", ".join(stack["frameworks"]) or "None detected")
            )
            sections.append("### Hotspots")
            if payload["timeline"]["hotspots"]:
                for hotspot in payload["timeline"]["hotspots"][:5]:
                    sections.append(
                        f"- `{hotspot['file']}`: {hotspot['changes']} changes"
                    )
            else:
                sections.append("- None detected.")
            sections.append("### Risks")
            has_risk = False
            for severity in ("critical", "warning", "info"):
                for item in payload["risk_map"][severity]:
                    has_risk = True
                    sections.append(
                        f"- [{severity.upper()}] {item['message']}"
                    )
            if not has_risk:
                sections.append("- None detected.")
        return "\n".join(sections)
