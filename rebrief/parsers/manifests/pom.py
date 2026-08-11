from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from rebrief.parsers.manifests.base import ManifestParseResult, empty_result


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
    for element in root.iter():
        if _local_tag(element.tag) != "dependency":
            continue
        for child in element:
            if _local_tag(child.tag) == "artifactId" and child.text:
                dependencies.append(child.text.strip())

    return {"dependencies": dependencies}
