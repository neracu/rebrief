from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from rebrief.parsers.manifests.base import ManifestParseResult, empty_result
from rebrief.parsers.manifests.versions import PackageSpec, parse_maven_coord


def _local_tag(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag


def parse(path: Path) -> ManifestParseResult:
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        return empty_result(f"Could not read {path.name}: {exc}")

    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        return empty_result(f"Could not parse {path.name}: {exc}")

    dependencies: list[str] = []
    packages: list[PackageSpec] = []
    for element in root.iter():
        if _local_tag(element.tag) != "dependency":
            continue
        group_id: str | None = None
        artifact_id: str | None = None
        version: str | None = None
        for child in element:
            tag = _local_tag(child.tag)
            if child.text is None:
                continue
            if tag == "groupId":
                group_id = child.text.strip()
            elif tag == "artifactId":
                artifact_id = child.text.strip()
            elif tag == "version":
                version = child.text.strip()
        if artifact_id:
            dependencies.append(artifact_id)
        if group_id and artifact_id and version:
            pkg = parse_maven_coord(group_id, artifact_id, version)
            if pkg is not None:
                packages.append(pkg)

    result: ManifestParseResult = {"dependencies": dependencies}
    if packages:
        result["packages"] = packages
    return result
