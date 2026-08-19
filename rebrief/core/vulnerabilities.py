from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Literal, TypedDict

from rebrief import __version__
from rebrief.core.confidence import Confidence
from rebrief.parsers.manifests.versions import PackageSpec

OSV_QUERYBATCH_URL = "https://api.osv.dev/v1/querybatch"
OSV_VULN_URL = "https://api.osv.dev/v1/vulns/{id}"
DEFAULT_TIMEOUT_SECONDS = 3.0
BATCH_CHUNK_SIZE = 1000
SKIP_MESSAGE = "Skipping remote vulnerability check (offline/timeout)"

Severity = Literal["critical", "warning"]


class VulnerabilityFinding(TypedDict):
    id: str
    package: str
    severity: Severity
    fixed_in: str
    summary: str
    confidence: str


class VulnerabilityReport(TypedDict):
    findings: list[VulnerabilityFinding]
    skipped: bool
    skip_message: str | None


Transport = Callable[[str, str, bytes | None, float], tuple[int, bytes]]


def _default_transport(
    method: str,
    url: str,
    body: bytes | None,
    timeout: float,
) -> tuple[int, bytes]:
    headers = {
        "User-Agent": f"rebrief/{__version__}",
        "Accept": "application/json",
    }
    request = urllib.request.Request(url, data=body, method=method, headers=headers)
    if body is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def _empty_report(*, skipped: bool = False, skip_message: str | None = None) -> VulnerabilityReport:
    return {
        "findings": [],
        "skipped": skipped,
        "skip_message": skip_message,
    }


def _parse_cvss_score(score_text: str) -> float | None:
    if not score_text:
        return None
    stripped = score_text.strip()
    try:
        return float(stripped)
    except ValueError:
        pass
    if "/" in stripped and stripped.startswith("CVSS:"):
        # Vector-only payloads do not include a numeric score.
        return None
    if "/" in stripped:
        candidate = stripped.split("/", 1)[0]
        try:
            return float(candidate)
        except ValueError:
            return None
    return None


def _qualitative_severity(value: str) -> Severity | None:
    normalized = value.strip().upper()
    if normalized in {"CRITICAL", "HIGH"}:
        return "critical"
    if normalized in {"MODERATE", "MEDIUM", "LOW"}:
        return "warning"
    return None


def _severity_from_vuln(vuln: dict[str, object]) -> Severity:
    max_cvss = 0.0
    has_cvss = False

    for entry in vuln.get("severity", []):
        if not isinstance(entry, dict):
            continue
        score = entry.get("score")
        if isinstance(score, str):
            parsed = _parse_cvss_score(score)
            if parsed is not None:
                has_cvss = True
                max_cvss = max(max_cvss, parsed)

    if has_cvss:
        return "critical" if max_cvss >= 8.0 else "warning"

    database_specific = vuln.get("database_specific")
    if isinstance(database_specific, dict):
        severity_value = database_specific.get("severity")
        if isinstance(severity_value, str):
            qualitative = _qualitative_severity(severity_value)
            if qualitative is not None:
                return qualitative

    return "warning"


def _extract_fixed_version(vuln: dict[str, object], package_name: str) -> str:
    for affected in vuln.get("affected", []):
        if not isinstance(affected, dict):
            continue
        pkg = affected.get("package")
        if isinstance(pkg, dict):
            name = pkg.get("name")
            if isinstance(name, str) and name != package_name:
                continue
        for range_entry in affected.get("ranges", []):
            if not isinstance(range_entry, dict):
                continue
            for event in range_entry.get("events", []):
                if not isinstance(event, dict):
                    continue
                fixed = event.get("fixed")
                if isinstance(fixed, str) and fixed:
                    return fixed
    return ""


def _extract_summary(vuln: dict[str, object]) -> str:
    summary = vuln.get("summary")
    if isinstance(summary, str) and summary.strip():
        return summary.strip()
    details = vuln.get("details")
    if isinstance(details, str) and details.strip():
        return details.strip().splitlines()[0]
    return "No summary available."


def _vuln_id(vuln: dict[str, object]) -> str:
    value = vuln.get("id")
    if isinstance(value, str) and value:
        return value
    for alias in vuln.get("aliases", []):
        if isinstance(alias, str) and alias:
            return alias
    return "UNKNOWN"


def _query_batch(
    packages: list[PackageSpec],
    transport: Transport,
    deadline: float,
) -> list[list[dict[str, str]]]:
    all_results: list[list[dict[str, str]]] = []
    queries = [
        {
            "package": {"name": pkg["name"], "ecosystem": pkg["ecosystem"]},
            "version": pkg["version"],
        }
        for pkg in packages
    ]

    for start in range(0, len(queries), BATCH_CHUNK_SIZE):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("OSV querybatch timed out")

        chunk = queries[start : start + BATCH_CHUNK_SIZE]
        payload = json.dumps({"queries": chunk}).encode("utf-8")
        status, body = transport("POST", OSV_QUERYBATCH_URL, payload, remaining)
        if status != 200:
            raise urllib.error.URLError(f"OSV querybatch returned HTTP {status}")

        data = json.loads(body.decode("utf-8"))
        results = data.get("results", [])
        if not isinstance(results, list):
            raise ValueError("Invalid OSV querybatch response")

        for entry in results:
            vulns: list[dict[str, str]] = []
            if isinstance(entry, dict):
                raw_vulns = entry.get("vulns", [])
                if isinstance(raw_vulns, list):
                    for item in raw_vulns:
                        if isinstance(item, dict):
                            vuln_id = item.get("id")
                            if isinstance(vuln_id, str):
                                modified = item.get("modified")
                                vulns.append(
                                    {
                                        "id": vuln_id,
                                        "modified": str(modified or ""),
                                    }
                                )
            all_results.append(vulns)

    return all_results


def _fetch_vuln(
    vuln_id: str,
    transport: Transport,
    timeout: float,
) -> dict[str, object] | None:
    if timeout <= 0:
        return None
    url = OSV_VULN_URL.format(id=urllib.request.quote(vuln_id, safe=""))
    status, body = transport("GET", url, None, timeout)
    if status != 200:
        return None
    data = json.loads(body.decode("utf-8"))
    if isinstance(data, dict):
        return data
    return None


def check_vulnerabilities(
    packages: list[PackageSpec],
    *,
    skip: bool = False,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    transport: Transport | None = None,
) -> VulnerabilityReport:
    if skip or not packages:
        return _empty_report()

    send = transport or _default_transport
    deadline = time.monotonic() + timeout

    try:
        batch_results = _query_batch(packages, send, deadline)
    except (TimeoutError, urllib.error.URLError, ValueError, json.JSONDecodeError, OSError):
        return _empty_report(skipped=True, skip_message=SKIP_MESSAGE)

    id_to_packages: dict[str, list[PackageSpec]] = {}
    unique_ids: set[str] = set()

    for pkg, vuln_refs in zip(packages, batch_results):
        for ref in vuln_refs:
            vuln_id = ref["id"]
            unique_ids.add(vuln_id)
            id_to_packages.setdefault(vuln_id, [])
            if pkg not in id_to_packages[vuln_id]:
                id_to_packages[vuln_id].append(pkg)

    if not unique_ids:
        return _empty_report()

    vuln_records: dict[str, dict[str, object]] = {}
    try:
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = {}
            for vuln_id in unique_ids:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("OSV vuln fetch timed out")
                futures[executor.submit(_fetch_vuln, vuln_id, send, remaining)] = vuln_id

            for future in as_completed(futures):
                vuln_id = futures[future]
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("OSV vuln fetch timed out")
                record = future.result()
                if record is not None:
                    vuln_records[vuln_id] = record
    except (TimeoutError, urllib.error.URLError, ValueError, json.JSONDecodeError, OSError):
        return _empty_report(skipped=True, skip_message=SKIP_MESSAGE)

    findings: list[VulnerabilityFinding] = []
    seen: set[tuple[str, str]] = set()

    for vuln_id, affected_packages in id_to_packages.items():
        vuln = vuln_records.get(vuln_id)
        if vuln is None:
            continue

        resolved_id = _vuln_id(vuln)
        severity = _severity_from_vuln(vuln)
        summary = _extract_summary(vuln)

        for pkg in affected_packages:
            key = (resolved_id, pkg["name"])
            if key in seen:
                continue
            seen.add(key)

            confidence = Confidence.HIGH.value if pkg["exact"] else Confidence.MEDIUM.value
            fixed_in = _extract_fixed_version(vuln, pkg["name"])

            findings.append(
                {
                    "id": resolved_id,
                    "package": pkg["name"],
                    "severity": severity,
                    "fixed_in": fixed_in,
                    "summary": summary,
                    "confidence": confidence,
                }
            )

    return {
        "findings": findings,
        "skipped": False,
        "skip_message": None,
    }
