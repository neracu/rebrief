from __future__ import annotations

from typing import TypedDict

from rebrief.parsers.manifests.versions import PackageSpec


class ManifestParseResult(TypedDict, total=False):
    dependencies: list[str]
    packages: list[PackageSpec]
    metadata: dict[str, str]
    error: str


def empty_result(error: str | None = None) -> ManifestParseResult:
    result: ManifestParseResult = {"dependencies": []}
    if error is not None:
        result["error"] = error
    return result
