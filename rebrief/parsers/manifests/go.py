from __future__ import annotations

import re
from pathlib import Path

from rebrief.parsers.manifests.base import ManifestParseResult, empty_result

_MODULE_RE = re.compile(r"^module\s+(\S+)")
_GO_VERSION_RE = re.compile(r"^go\s+(\S+)")
_REQUIRE_LINE_RE = re.compile(r"^\s*(\S+)\s+(\S+)")


def parse(path: Path) -> ManifestParseResult:
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        return empty_result(f"Could not read {path.name}: {exc}")

    metadata: dict[str, str] = {}
    dependencies: list[str] = []
    in_require_block = False

    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("//"):
            continue

        module_match = _MODULE_RE.match(stripped)
        if module_match:
            metadata["module"] = module_match.group(1)
            continue

        go_version_match = _GO_VERSION_RE.match(stripped)
        if go_version_match:
            metadata["go_version"] = go_version_match.group(1)
            continue

        if stripped == "require (":
            in_require_block = True
            continue

        if in_require_block:
            if stripped == ")":
                in_require_block = False
                continue
            if "// indirect" in stripped:
                continue
            require_match = _REQUIRE_LINE_RE.match(stripped)
            if require_match:
                dependencies.append(require_match.group(1))
            continue

        if stripped.startswith("require ") and "// indirect" not in stripped:
            remainder = stripped[len("require "):].strip()
            require_match = _REQUIRE_LINE_RE.match(remainder)
            if require_match:
                dependencies.append(require_match.group(1))

    result: ManifestParseResult = {"dependencies": dependencies}
    if metadata:
        result["metadata"] = metadata
    return result
