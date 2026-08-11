from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator, TypedDict

from rebrief.core.ignore import IgnoreMatcher
from rebrief.parsers.manifests import (
    MANIFEST_FILES,
    MANIFEST_LANGUAGES,
    parse_manifest,
)

FRAMEWORK_SIGNATURES: dict[str, str] = {
    "next.config.js": "Next.js",
    "next.config.mjs": "Next.js",
    "manage.py": "Django",
    "nuxt.config.js": "Nuxt.js",
    "nuxt.config.ts": "Nuxt.js",
    "vite.config.js": "Vite",
    "vite.config.ts": "Vite",
    "angular.json": "Angular",
    "svelte.config.js": "Svelte",
    "remix.config.js": "Remix",
    "artisan": "Laravel",
}

FRAMEWORK_DEPENDENCY_RULES: tuple[tuple[str, str], ...] = (
    ("react", "React"),
    ("next", "Next.js"),
    ("vue", "Vue"),
    ("@angular/core", "Angular"),
    ("svelte", "Svelte"),
    ("express", "Express"),
    ("@nestjs/core", "NestJS"),
    ("@remix-run/node", "Remix"),
    ("django", "Django"),
    ("djangorestframework", "Django REST Framework"),
    ("fastapi", "FastAPI"),
    ("flask", "Flask"),
    ("gin-gonic/gin", "Gin"),
    ("labstack/echo", "Echo"),
    ("gofiber/fiber", "Fiber"),
    ("actix-web", "Actix Web"),
    ("axum", "Axum"),
    ("rocket", "Rocket"),
    ("spring-boot", "Spring Boot"),
    ("quarkus", "Quarkus"),
    ("micronaut", "Micronaut"),
    ("laravel/framework", "Laravel"),
    ("symfony/framework-bundle", "Symfony"),
    ("slim/slim", "Slim"),
    ("rails", "Rails"),
    ("sinatra", "Sinatra"),
)

MAX_DEPTH = 3


def _dependency_matches(signal: str, dep: str) -> bool:
    signal_lower = signal.lower()
    dep_lower = dep.lower()
    if dep_lower == signal_lower:
        return True
    if "/" in dep_lower or ":" in dep_lower:
        return signal_lower in dep_lower
    if "-" in signal_lower:
        return signal_lower in dep_lower
    if len(signal_lower) >= 7 and signal_lower in dep_lower:
        return True
    return False


class StackResult(TypedDict):
    languages: list[str]
    manifests: list[str]
    frameworks: list[str]
    dependencies: list[str]
    is_empty: bool
    manifest_warnings: list[str]


class StackParser:
    def __init__(self, repo_path: str) -> None:
        self._repo_path = Path(repo_path)
        self._ignore_matcher = IgnoreMatcher(repo_path)

    def parse(self) -> StackResult:
        is_empty = not any(True for _ in self._walk_files())
        manifest_paths = self._find_files(MANIFEST_FILES)
        signature_paths = self._find_files(tuple(FRAMEWORK_SIGNATURES.keys()))
        dependencies, manifest_warnings = self._extract_dependencies(manifest_paths)

        languages = sorted(
            {
                MANIFEST_LANGUAGES[Path(path).name]
                for path in manifest_paths
                if Path(path).name in MANIFEST_LANGUAGES
            }
        )
        frameworks = sorted(
            self._detect_signature_frameworks(signature_paths)
            | self._detect_dependency_frameworks(dependencies, signature_paths)
        )

        return {
            "languages": languages,
            "manifests": manifest_paths,
            "frameworks": frameworks,
            "dependencies": dependencies,
            "is_empty": is_empty,
            "manifest_warnings": manifest_warnings,
        }

    def _walk_files(self) -> Iterator[Path]:
        if not self._repo_path.is_dir():
            return

        for root, dirs, files in os.walk(self._repo_path):
            root_path = Path(root)
            relative_root = root_path.relative_to(self._repo_path)
            depth = len(relative_root.parts)

            relative_root_str = (
                relative_root.as_posix() if relative_root.parts else ""
            )
            dirs[:] = sorted(
                directory
                for directory in dirs
                if depth < MAX_DEPTH
                and not self._ignore_matcher.should_prune_dir(
                    directory, relative_root_str
                )
            )

            for filename in sorted(files):
                yield root_path / filename

    def _find_files(self, names: tuple[str, ...]) -> list[str]:
        wanted = set(names)
        found: list[str] = []

        for file_path in self._walk_files():
            if file_path.name not in wanted:
                continue
            found.append(file_path.relative_to(self._repo_path).as_posix())

        return sorted(set(found))

    def _detect_signature_frameworks(self, signature_paths: list[str]) -> set[str]:
        frameworks: set[str] = set()

        for path in signature_paths:
            framework = FRAMEWORK_SIGNATURES.get(Path(path).name)
            if framework is not None:
                frameworks.add(framework)

        return frameworks

    def _detect_dependency_frameworks(
        self,
        dependencies: list[str],
        signature_paths: list[str],
    ) -> set[str]:
        frameworks: set[str] = set()
        normalized = {dep.lower() for dep in dependencies}

        for signal, framework in FRAMEWORK_DEPENDENCY_RULES:
            if any(_dependency_matches(signal, dep) for dep in normalized):
                frameworks.add(framework)

        if any(Path(path).name == "manage.py" for path in signature_paths):
            frameworks.add("Django")

        return frameworks

    def _extract_dependencies(
        self, manifest_paths: list[str]
    ) -> tuple[list[str], list[str]]:
        dependencies: list[str] = []
        manifest_warnings: list[str] = []

        for relative_path in manifest_paths:
            path = self._repo_path / relative_path
            result = parse_manifest(path)

            dependencies.extend(result.get("dependencies", []))

            error = result.get("error")
            if error:
                manifest_warnings.append(
                    f"Malformed manifest: {relative_path} ({error})"
                )

        return sorted(set(dependencies)), sorted(manifest_warnings)
