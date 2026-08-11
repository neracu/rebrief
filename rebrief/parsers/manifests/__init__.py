from __future__ import annotations

from pathlib import Path
from typing import Callable

from rebrief.parsers.manifests.base import ManifestParseResult
from rebrief.parsers.manifests.cargo import parse as parse_cargo
from rebrief.parsers.manifests.composer import parse as parse_composer
from rebrief.parsers.manifests.gemfile import parse as parse_gemfile
from rebrief.parsers.manifests.go import parse as parse_go
from rebrief.parsers.manifests.gradle import parse as parse_gradle
from rebrief.parsers.manifests.package_json import parse as parse_package_json
from rebrief.parsers.manifests.pom import parse as parse_pom
from rebrief.parsers.manifests.pyproject import parse as parse_pyproject
from rebrief.parsers.manifests.requirements import parse as parse_requirements

MANIFEST_FILES: tuple[str, ...] = (
    "package.json",
    "requirements.txt",
    "poetry.lock",
    "pyproject.toml",
    "go.mod",
    "Cargo.toml",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "composer.json",
    "Gemfile",
)

MANIFEST_LANGUAGES: dict[str, str] = {
    "package.json": "JavaScript/TypeScript",
    "requirements.txt": "Python",
    "poetry.lock": "Python",
    "pyproject.toml": "Python",
    "go.mod": "Go",
    "Cargo.toml": "Rust",
    "pom.xml": "Java",
    "build.gradle": "Java",
    "build.gradle.kts": "Kotlin",
    "composer.json": "PHP",
    "Gemfile": "Ruby",
}

MANIFEST_PARSERS: dict[str, Callable[[Path], ManifestParseResult]] = {
    "package.json": parse_package_json,
    "requirements.txt": parse_requirements,
    "pyproject.toml": parse_pyproject,
    "go.mod": parse_go,
    "Cargo.toml": parse_cargo,
    "pom.xml": parse_pom,
    "build.gradle": parse_gradle,
    "build.gradle.kts": parse_gradle,
    "composer.json": parse_composer,
    "Gemfile": parse_gemfile,
}


def parse_manifest(path: Path) -> ManifestParseResult:
    parser = MANIFEST_PARSERS.get(path.name)
    if parser is None:
        return {"dependencies": []}
    return parser(path)
