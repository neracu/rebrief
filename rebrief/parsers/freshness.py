from __future__ import annotations

import re
import subprocess
import time
from collections import defaultdict
from pathlib import Path
from typing import Literal, TypedDict

from rebrief.core.confidence import Confidence
from rebrief.core.ignore import IgnoreMatcher
from rebrief.parsers.stack import StackResult

DocDriftSeverity = Literal["warning", "info"]
DocDriftKind = Literal["stack", "path", "env"]

ROOT_DOC_FILES: tuple[str, ...] = (
    "README.md",
    "CONTRIBUTING.md",
    ".cursorrules",
    "CLAUDE.md",
    "AGENTS.md",
)

ENV_EXAMPLE_FILES: tuple[str, ...] = (
    ".env.example",
    "env.example",
    ".env.sample",
    ".env.template",
)

CURSOR_RULES_DIR = Path(".cursor") / "rules"
MDC_SUFFIX = ".mdc"

KNOWN_FILENAMES: frozenset[str] = frozenset(
    {
        "readme.md",
        "contributing.md",
        "package.json",
        "package-lock.json",
        "pyproject.toml",
        "requirements.txt",
        "poetry.lock",
        "go.mod",
        "cargo.toml",
        "pom.xml",
        "build.gradle",
        "build.gradle.kts",
        "composer.json",
        "gemfile",
        "claude.md",
        "agents.md",
        ".cursorrules",
        ".env.example",
        "env.example",
        "manage.py",
        "dockerfile",
        "docker-compose.yml",
        "tsconfig.json",
        "next.config.js",
        "next.config.mjs",
        "vite.config.js",
        "vite.config.ts",
        "angular.json",
        "svelte.config.js",
        "nuxt.config.js",
        "nuxt.config.ts",
        "remix.config.js",
        "pnpm-workspace.yaml",
        "lerna.json",
    }
)

GENERATED_ARTIFACTS: frozenset[str] = frozenset(
    {
        "rebrief.md",
        "rebrief.json",
        "rebrief.xml",
        "rebrief.html",
        "rebrief-system.md",
        "rebrief-system.json",
        "rebrief-system.xml",
        "handoff.md",
    }
)

# documented keyword -> family id
STACK_KEYWORDS: dict[str, str] = {
    "vue": "frontend",
    "vue 2": "frontend",
    "vue 3": "frontend",
    "react": "frontend",
    "angular": "frontend",
    "svelte": "frontend",
    "next.js": "meta_framework",
    "nextjs": "meta_framework",
    "nuxt": "meta_framework",
    "remix": "meta_framework",
    "webpack": "bundler",
    "vite": "bundler",
    "rollup": "bundler",
    "parcel": "bundler",
    "django": "python_web",
    "flask": "python_web",
    "fastapi": "python_web",
    "express": "node_web",
    "nestjs": "node_web",
    "spring boot": "java_web",
    "laravel": "php_web",
    "rails": "ruby_web",
    "typescript": "language",
    "javascript": "language",
    "python": "language",
    "go": "language",
    "golang": "language",
    "rust": "language",
    "java": "language",
    "kotlin": "language",
    "php": "language",
    "ruby": "language",
}

KEYWORD_TO_DISPLAY: dict[str, str] = {
    "vue": "Vue",
    "vue 2": "Vue",
    "vue 3": "Vue",
    "react": "React",
    "angular": "Angular",
    "svelte": "Svelte",
    "next.js": "Next.js",
    "nextjs": "Next.js",
    "nuxt": "Nuxt",
    "remix": "Remix",
    "webpack": "Webpack",
    "vite": "Vite",
    "rollup": "Rollup",
    "parcel": "Parcel",
    "django": "Django",
    "flask": "Flask",
    "fastapi": "FastAPI",
    "express": "Express",
    "nestjs": "NestJS",
    "spring boot": "Spring Boot",
    "laravel": "Laravel",
    "rails": "Rails",
    "typescript": "TypeScript",
    "javascript": "JavaScript",
    "python": "Python",
    "go": "Go",
    "golang": "Go",
    "rust": "Rust",
    "java": "Java",
    "kotlin": "Kotlin",
    "php": "PHP",
    "ruby": "Ruby",
}

# Map detected stack signals to families / display names
DETECTED_STACK_SIGNALS: dict[str, tuple[str, str]] = {
    "react": ("frontend", "React"),
    "vue": ("frontend", "Vue"),
    "@angular/core": ("frontend", "Angular"),
    "angular": ("frontend", "Angular"),
    "svelte": ("frontend", "Svelte"),
    "next": ("meta_framework", "Next.js"),
    "nuxt": ("meta_framework", "Nuxt"),
    "@remix-run/node": ("meta_framework", "Remix"),
    "remix": ("meta_framework", "Remix"),
    "vite": ("bundler", "Vite"),
    "webpack": ("bundler", "Webpack"),
    "django": ("python_web", "Django"),
    "flask": ("python_web", "Flask"),
    "fastapi": ("python_web", "FastAPI"),
    "express": ("node_web", "Express"),
    "@nestjs/core": ("node_web", "NestJS"),
    "spring-boot": ("java_web", "Spring Boot"),
    "laravel/framework": ("php_web", "Laravel"),
    "rails": ("ruby_web", "Rails"),
}

FRAMEWORK_TO_DISPLAY: dict[str, str] = {
    "React": "React",
    "Vue": "Vue",
    "Angular": "Angular",
    "Svelte": "Svelte",
    "Next.js": "Next.js",
    "Nuxt.js": "Nuxt",
    "Remix": "Remix",
    "Vite": "Vite",
    "Django": "Django",
    "Flask": "Flask",
    "FastAPI": "FastAPI",
    "Express": "Express",
    "NestJS": "NestJS",
    "Spring Boot": "Spring Boot",
    "Laravel": "Laravel",
    "Rails": "Rails",
}

LANGUAGE_TO_DISPLAY: dict[str, str] = {
    "JavaScript/TypeScript": "JavaScript/TypeScript",
    "Python": "Python",
    "Go": "Go",
    "Rust": "Rust",
    "Java": "Java",
    "Kotlin": "Kotlin",
    "PHP": "PHP",
    "Ruby": "Ruby",
}

PATH_BACKTICK_RE = re.compile(r"`([^`\n]+)`")
PATH_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
PATH_SLASH_RE = re.compile(
    r"(?<![\w./])(?:\./)?(?:src|lib|app|apps|packages|components|pages|"
    r"services|api|backend|frontend|docs|tests?|__tests__|config|scripts|"
    r"public|static|assets)(?:/[\w.-]+)+/?",
    re.IGNORECASE,
)
ENV_ASSIGNMENT_RE = re.compile(
    r"^(?:export\s+)?([A-Z][A-Z0-9_]*)\s*=",
    re.MULTILINE,
)
ENV_PROCESS_RE = re.compile(
    r"(?:process\.env\.|os\.environ\[['\"]|os\.environ\.get\(['\"]|"
    r"os\.getenv\(['\"]|getenv\(['\"]|ENV\[['\"])([A-Z][A-Z0-9_]*)",
)
ENV_DOLLAR_RE = re.compile(r"\$([A-Z][A-Z0-9_]{2,})\b")

GENERIC_PATH_WORDS: frozenset[str] = frozenset(
    {
        "src",
        "lib",
        "app",
        "docs",
        "test",
        "tests",
        "config",
        "api",
        "env",
    }
)

VALID_PATH_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".md",
        ".json",
        ".js",
        ".mjs",
        ".ts",
        ".tsx",
        ".jsx",
        ".py",
        ".toml",
        ".yaml",
        ".yml",
        ".xml",
        ".html",
        ".lock",
        ".mod",
        ".cfg",
        ".mdc",
        ".kts",
        ".gradle",
        ".gemspec",
        ".example",
        ".sample",
        ".template",
        ".ini",
        ".txt",
    }
)

PATH_ROOT_SEGMENTS: frozenset[str] = frozenset(
    {
        "src",
        "lib",
        "app",
        "apps",
        "packages",
        "components",
        "pages",
        "services",
        "api",
        "backend",
        "frontend",
        "docs",
        "tests",
        "test",
        "__tests__",
        "config",
        "scripts",
        "public",
        "static",
        "assets",
        "web",
        "rebrief",
        ".cursor",
        ".github",
        ".venv",
        "venv",
        "node_modules",
    }
)

TOOL_INTERNAL_PREFIXES: tuple[str, ...] = (
    ".rebrief",
    ".rebrief/",
)

OPTIONAL_CONFIG_SUFFIXES: tuple[str, ...] = (
    "mcp.json",
    "claude_desktop_config.json",
)

MANIFEST_CATALOG_THRESHOLD = 3

SCORE_WEIGHTS = {
    "path": 0.35,
    "stack": 0.35,
    "env": 0.15,
    "recency": 0.15,
}

RECENCY_GRACE_ACTIVE_DAYS = 30
RECENCY_GRACE_QUIET_DAYS = 90
RECENCY_COMMIT_THRESHOLD = 10


class DocDriftItem(TypedDict):
    severity: DocDriftSeverity
    confidence: str
    kind: DocDriftKind
    source: str
    message: str


class DocDriftComponents(TypedDict):
    path_ratio: float
    stack_ratio: float
    env_ratio: float
    recency_ratio: float


class DocDriftReport(TypedDict):
    freshness_score: int
    freshness_label: str
    scanned_files: list[str]
    components: DocDriftComponents
    items: list[DocDriftItem]


def empty_doc_drift_report() -> DocDriftReport:
    return {
        "freshness_score": 100,
        "freshness_label": "Fresh",
        "scanned_files": [],
        "components": {
            "path_ratio": 1.0,
            "stack_ratio": 1.0,
            "env_ratio": 1.0,
            "recency_ratio": 1.0,
        },
        "items": [],
    }


def freshness_label(score: int) -> str:
    if score >= 90:
        return "Fresh"
    if score >= 70:
        return "Needs Review"
    return "Stale"


def compute_freshness_score(components: DocDriftComponents) -> int:
    weighted = (
        SCORE_WEIGHTS["path"] * components["path_ratio"]
        + SCORE_WEIGHTS["stack"] * components["stack_ratio"]
        + SCORE_WEIGHTS["env"] * components["env_ratio"]
        + SCORE_WEIGHTS["recency"] * components["recency_ratio"]
    )
    return round(100 * weighted)


def _strip_relative_prefix(candidate: str) -> str:
    if candidate.startswith("./"):
        return candidate[2:]
    if candidate.startswith(".\\"):
        return candidate[2:]
    return candidate


class FreshnessParser:
    def __init__(self, repo_path: str, stack: StackResult) -> None:
        self._repo_path = Path(repo_path)
        self._stack = stack
        self._ignore_matcher = IgnoreMatcher(repo_path)
        self._manifest_basenames = {
            Path(manifest).name.casefold() for manifest in stack["manifests"]
        }

    def parse(self) -> DocDriftReport:
        if not self._repo_path.is_dir():
            return empty_doc_drift_report()

        doc_files = self._collect_doc_files()
        if not doc_files:
            return empty_doc_drift_report()

        scanned_files = sorted(doc_files.keys())
        doc_text_by_source = doc_files

        items: list[DocDriftItem] = []
        path_valid, path_total = self._detect_path_drift(doc_text_by_source, items)
        stack_conflicts, stack_documented = self._detect_stack_drift(
            doc_text_by_source, items
        )
        env_gaps, env_union = self._detect_env_drift(doc_text_by_source, items)

        path_ratio = path_valid / path_total if path_total else 1.0
        stack_ratio = (
            1.0 - (stack_conflicts / stack_documented) if stack_documented else 1.0
        )
        env_ratio = 1.0 - (env_gaps / env_union) if env_union else 1.0
        recency_ratio = self._compute_recency_ratio(scanned_files)

        components: DocDriftComponents = {
            "path_ratio": round(path_ratio, 4),
            "stack_ratio": round(stack_ratio, 4),
            "env_ratio": round(env_ratio, 4),
            "recency_ratio": round(recency_ratio, 4),
        }
        score = compute_freshness_score(components)

        return {
            "freshness_score": score,
            "freshness_label": freshness_label(score),
            "scanned_files": scanned_files,
            "components": components,
            "items": items,
        }

    def _collect_doc_files(self) -> dict[str, str]:
        found: dict[str, str] = {}

        if not self._repo_path.is_dir():
            return found

        root_files = {
            entry.name.casefold(): entry
            for entry in self._repo_path.iterdir()
            if entry.is_file()
        }
        for canonical in ROOT_DOC_FILES:
            path = root_files.get(canonical.casefold())
            if path is not None:
                found[canonical] = self._read_file(path)

        docs_dir = self._repo_path / "docs"
        if docs_dir.is_dir():
            for path in sorted(docs_dir.rglob("*.md")):
                if not path.is_file():
                    continue
                relative = path.relative_to(self._repo_path).as_posix()
                if self._ignore_matcher.is_ignored(relative, is_dir=False):
                    continue
                found[relative] = self._read_file(path)

        cursor_rules = self._repo_path / CURSOR_RULES_DIR
        if cursor_rules.is_dir():
            for path in sorted(cursor_rules.rglob("*")):
                if not path.is_file() or path.suffix.casefold() != MDC_SUFFIX:
                    continue
                relative = path.relative_to(self._repo_path).as_posix()
                if self._ignore_matcher.is_ignored(relative, is_dir=False):
                    continue
                found[relative] = self._read_file(path)

        return found

    def _read_file(self, path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return ""

    def _detect_stack_drift(
        self,
        doc_files: dict[str, str],
        items: list[DocDriftItem],
    ) -> tuple[int, int]:
        detected_families = self._detected_stack_signals()
        documented_keywords = self._find_documented_stack_keywords(doc_files)
        catalog_families = self._catalog_families_by_source(documented_keywords)

        conflicts = 0
        documented_count = 0
        seen_conflicts: set[tuple[str, str, str]] = set()

        for source, keyword, family, display in documented_keywords:
            if family in catalog_families.get(source, set()):
                continue

            canonical = KEYWORD_TO_DISPLAY.get(keyword, display)
            detected_in_family = detected_families.get(family, set())
            if not detected_in_family:
                continue

            documented_count += 1
            if self._display_matches_detected(canonical, detected_in_family):
                continue

            conflict_key = (source, family, canonical.casefold())
            if conflict_key in seen_conflicts:
                continue
            seen_conflicts.add(conflict_key)
            conflicts += 1

            actual = ", ".join(f'"{name}"' for name in sorted(detected_in_family))
            items.append(
                {
                    "severity": "warning",
                    "confidence": Confidence.HIGH.value,
                    "kind": "stack",
                    "source": source,
                    "message": (
                        f'{source} references "{canonical}" but project '
                        f"depends on {actual}"
                    ),
                }
            )

        return conflicts, documented_count

    def _catalog_families_by_source(
        self,
        documented_keywords: list[tuple[str, str, str, str]],
    ) -> dict[str, set[str]]:
        rivals_by_source_family: dict[str, dict[str, set[str]]] = defaultdict(
            lambda: defaultdict(set)
        )
        for source, keyword, family, display in documented_keywords:
            canonical = KEYWORD_TO_DISPLAY.get(keyword, display)
            rivals_by_source_family[source][family].add(canonical.casefold())

        catalog: dict[str, set[str]] = {}
        for source, families in rivals_by_source_family.items():
            catalog[source] = {
                family
                for family, rivals in families.items()
                if len(rivals) >= 2
            }
        return catalog

    def _detected_stack_signals(self) -> dict[str, set[str]]:
        families: dict[str, set[str]] = defaultdict(set)

        for framework in self._stack["frameworks"]:
            display = FRAMEWORK_TO_DISPLAY.get(framework, framework)
            mapped = False
            for _signal, (family, mapped_display) in DETECTED_STACK_SIGNALS.items():
                if mapped_display.lower() == framework.lower():
                    families[family].add(mapped_display)
                    mapped = True
                    break
            if not mapped:
                name_lower = framework.lower()
                for _signal, (family, mapped_display) in DETECTED_STACK_SIGNALS.items():
                    if _signal in name_lower or name_lower in _signal:
                        families[family].add(mapped_display)
                        break
                else:
                    families["frontend"].add(display)

        deps_lower = " ".join(dep.lower() for dep in self._stack["dependencies"])
        for signal, (family, display) in DETECTED_STACK_SIGNALS.items():
            if signal in deps_lower:
                families[family].add(display)

        for language in self._stack["languages"]:
            display = LANGUAGE_TO_DISPLAY.get(language, language)
            families["language"].add(display)

        return dict(families)

    def _display_matches_detected(
        self, documented: str, detected: set[str]
    ) -> bool:
        doc_lower = documented.lower()
        for name in detected:
            name_lower = name.lower()
            if doc_lower == name_lower:
                return True
            if doc_lower in name_lower or name_lower in doc_lower:
                return True
        if doc_lower == "javascript" and any(
            "javascript" in d.lower() for d in detected
        ):
            return True
        if doc_lower == "typescript" and any(
            "typescript" in d.lower() for d in detected
        ):
            return True
        if doc_lower == "golang" and "Go" in detected:
            return True
        langs = {lang.lower() for lang in self._stack["languages"]}
        if doc_lower in langs:
            return True
        if doc_lower == "javascript" and "javascript/typescript" in langs:
            return True
        if doc_lower == "typescript" and "javascript/typescript" in langs:
            return True
        return False

    def _find_documented_stack_keywords(
        self, doc_files: dict[str, str]
    ) -> list[tuple[str, str, str, str]]:
        """Return (source, keyword, family, display) for each documented stack hit."""
        hits: list[tuple[str, str, str, str]] = []
        seen: set[tuple[str, str]] = set()

        sorted_keywords = sorted(STACK_KEYWORDS.keys(), key=len, reverse=True)
        for source, text in doc_files.items():
            lowered = text.lower()
            for keyword in sorted_keywords:
                pattern = re.compile(
                    rf"\b{re.escape(keyword)}\b",
                    re.IGNORECASE,
                )
                if not pattern.search(lowered):
                    continue
                key = (source, keyword)
                if key in seen:
                    continue
                seen.add(key)
                family = STACK_KEYWORDS[keyword]
                display = KEYWORD_TO_DISPLAY.get(keyword, keyword.title())
                hits.append((source, keyword, family, display))

        deduped: list[tuple[str, str, str, str]] = []
        seen_canonical: set[tuple[str, str, str]] = set()
        for source, keyword, family, display in hits:
            canonical = KEYWORD_TO_DISPLAY.get(keyword, display).casefold()
            key = (source, family, canonical)
            if key in seen_canonical:
                continue
            seen_canonical.add(key)
            deduped.append((source, keyword, family, display))

        return deduped

    def _detect_path_drift(
        self,
        doc_files: dict[str, str],
        items: list[DocDriftItem],
    ) -> tuple[int, int]:
        valid = 0
        total = 0
        seen_missing: set[tuple[str, str]] = set()
        manifest_catalog_sources = self._manifest_catalog_sources(doc_files)

        for source, text in doc_files.items():
            code_block_spans = self._code_block_spans(text)
            for raw_path, offset in self._extract_paths_with_offsets(text):
                if self._offset_in_code_block(offset, code_block_spans):
                    continue
                if not self._is_path_like_token(raw_path):
                    continue
                normalized = self._normalize_path(raw_path)
                if normalized is None:
                    continue
                if self._skip_optional_path(normalized):
                    continue
                if self._skip_manifest_catalog_path(
                    source, normalized, manifest_catalog_sources
                ):
                    continue
                total += 1
                if self._path_exists(normalized):
                    valid += 1
                else:
                    key = (source, normalized)
                    if key not in seen_missing:
                        seen_missing.add(key)
                        items.append(
                            {
                                "severity": "warning",
                                "confidence": Confidence.HIGH.value,
                                "kind": "path",
                                "source": source,
                                "message": (
                                    f"{source} references `{normalized}` "
                                    "which no longer exists in the codebase"
                                ),
                            }
                        )

        return valid, total

    def _code_block_spans(self, text: str) -> list[tuple[int, int]]:
        spans: list[tuple[int, int]] = []
        fence = re.compile(r"^```", re.MULTILINE)
        matches = list(fence.finditer(text))
        for index in range(0, len(matches) - 1, 2):
            start = matches[index].end()
            end = matches[index + 1].start()
            spans.append((start, end))
        return spans

    def _offset_in_code_block(
        self, offset: int, spans: list[tuple[int, int]]
    ) -> bool:
        return any(start <= offset < end for start, end in spans)

    def _skip_optional_path(self, normalized: str) -> bool:
        lowered = normalized.replace("\\", "/").casefold()
        if any(lowered == prefix.casefold() or lowered.startswith(prefix.casefold())
               for prefix in TOOL_INTERNAL_PREFIXES):
            return True
        return any(lowered.endswith(suffix.casefold()) for suffix in OPTIONAL_CONFIG_SUFFIXES)

    def _manifest_catalog_sources(self, doc_files: dict[str, str]) -> set[str]:
        catalogs: set[str] = set()
        for source, text in doc_files.items():
            manifest_refs = 0
            for raw_path in self._extract_paths(text):
                if not self._is_path_like_token(raw_path):
                    continue
                normalized = self._normalize_path(raw_path)
                if normalized is None or "/" in normalized or "\\" in normalized:
                    continue
                if normalized.casefold() not in KNOWN_FILENAMES:
                    continue
                if self._path_exists(normalized):
                    continue
                manifest_refs += 1
            if manifest_refs >= MANIFEST_CATALOG_THRESHOLD:
                catalogs.add(source)
        return catalogs

    def _skip_manifest_catalog_path(
        self,
        source: str,
        normalized: str,
        manifest_catalog_sources: set[str],
    ) -> bool:
        if source not in manifest_catalog_sources:
            return False
        if "/" in normalized or "\\" in normalized:
            return False
        return normalized.casefold() in KNOWN_FILENAMES

    def _is_path_like_token(self, raw: str) -> bool:
        candidate = raw.strip().strip('"').strip("'")
        if not candidate:
            return False
        if candidate.startswith("-"):
            return False
        if " " in candidate:
            return False
        if any(char in candidate for char in "(){}>=,"):
            return False
        if candidate.startswith("/"):
            remainder = candidate.lstrip("/")
            if "/" not in remainder and "." not in remainder:
                return False
        normalized = candidate.replace("\\", "/")
        if "/" in normalized:
            parts = [part for part in normalized.split("/") if part]
            if not parts:
                return False
            if not any(part.lower() in PATH_ROOT_SEGMENTS for part in parts):
                suffix = Path(parts[-1]).suffix.lower()
                if not suffix or suffix not in VALID_PATH_EXTENSIONS:
                    return False
            if (
                len(parts) == 2
                and "." not in normalized
                and parts[0].lower() not in PATH_ROOT_SEGMENTS
                and parts[1].lower() not in PATH_ROOT_SEGMENTS
            ):
                return False
            return True
        if candidate.startswith("."):
            if candidate.count(".") >= 2 or len(candidate) > 5:
                return True
            return False
        lowered = candidate.casefold()
        if lowered in KNOWN_FILENAMES:
            return True
        suffix = Path(candidate).suffix.lower()
        return bool(suffix and suffix in VALID_PATH_EXTENSIONS)

    def _extract_paths(self, text: str) -> list[str]:
        return [raw_path for raw_path, _offset in self._extract_paths_with_offsets(text)]

    def _extract_paths_with_offsets(self, text: str) -> list[tuple[str, int]]:
        paths: list[tuple[str, int]] = []
        for match in PATH_BACKTICK_RE.finditer(text):
            paths.append((match.group(1).strip(), match.start()))
        for match in PATH_LINK_RE.finditer(text):
            paths.append((match.group(1).strip(), match.start()))
        for match in PATH_SLASH_RE.finditer(text):
            paths.append((match.group(0).strip(), match.start()))
        return paths

    def _normalize_path(self, raw: str) -> str | None:
        candidate = raw.strip().strip('"').strip("'")
        if not candidate:
            return None
        if candidate.startswith(("http://", "https://", "mailto:", "#")):
            return None
        if "://" in candidate:
            return None
        candidate = candidate.split("#", 1)[0].split("?", 1)[0]
        candidate = _strip_relative_prefix(candidate)
        if not candidate or candidate.endswith((".png", ".jpg", ".gif", ".svg", ".ico")):
            return None
        basename = Path(candidate).name.casefold()
        if basename in GENERATED_ARTIFACTS:
            return None
        if "/" not in candidate and candidate.casefold() in GENERIC_PATH_WORDS:
            return None
        parts = [part for part in candidate.replace("\\", "/").split("/") if part and part != "."]
        if not parts:
            return None
        if len(parts) == 1 and parts[0].casefold() in GENERIC_PATH_WORDS:
            return None
        return "/".join(parts)

    def _path_exists(self, relative: str) -> bool:
        target = self._repo_path / relative
        if target.exists():
            return True
        basename = Path(relative).name.casefold()
        return basename in self._manifest_basenames

    def _detect_env_drift(
        self,
        doc_files: dict[str, str],
        items: list[DocDriftItem],
    ) -> tuple[int, int]:
        example_keys = self._parse_env_example_keys()
        if not example_keys:
            return 0, 0

        doc_keys = self._parse_documented_env_keys(doc_files)
        union = example_keys | doc_keys
        gaps = 0

        missing_from_docs = sorted(example_keys - doc_keys)
        extra_in_docs = sorted(doc_keys - example_keys)

        for key in missing_from_docs:
            gaps += 1
            items.append(
                {
                    "severity": "warning",
                    "confidence": Confidence.MEDIUM.value,
                    "kind": "env",
                    "source": self._env_example_source(),
                    "message": (
                        f"`.env.example` defines `{key}` but it is not "
                        "documented in project docs"
                    ),
                }
            )

        for key in extra_in_docs:
            gaps += 1
            items.append(
                {
                    "severity": "info",
                    "confidence": Confidence.MEDIUM.value,
                    "kind": "env",
                    "source": "documentation",
                    "message": (
                        f"Documentation references env var `{key}` but it is "
                        "missing from `.env.example`"
                    ),
                }
            )

        return gaps, len(union) if union else 0

    def _env_example_source(self) -> str:
        for name in ENV_EXAMPLE_FILES:
            if (self._repo_path / name).is_file():
                return name
        return ".env.example"

    def _parse_env_example_keys(self) -> set[str]:
        keys: set[str] = set()
        for name in ENV_EXAMPLE_FILES:
            path = self._repo_path / name
            if not path.is_file():
                continue
            text = self._read_file(path)
            for match in ENV_ASSIGNMENT_RE.finditer(text):
                keys.add(match.group(1))
        return keys

    def _parse_documented_env_keys(self, doc_files: dict[str, str]) -> set[str]:
        keys: set[str] = set()
        combined = "\n".join(doc_files.values())
        for pattern in (ENV_PROCESS_RE, ENV_DOLLAR_RE):
            for match in pattern.finditer(combined):
                keys.add(match.group(1))
        return keys

    def _compute_recency_ratio(self, scanned_files: list[str]) -> float:
        doc_mtime = self._latest_doc_mtime(scanned_files)
        code_mtime = self._latest_code_commit_time()

        if doc_mtime is None:
            return 1.0
        if code_mtime is None:
            return 1.0

        grace_days = self._recency_grace_days()
        age_days = max(0.0, (code_mtime - doc_mtime) / 86400.0)
        if age_days <= grace_days:
            return 1.0
        excess = age_days - grace_days
        decay_window = grace_days
        ratio = max(0.0, 1.0 - (excess / decay_window))
        return round(ratio, 4)

    def _latest_doc_mtime(self, scanned_files: list[str]) -> float | None:
        latest: float | None = None
        for relative in scanned_files:
            path = self._repo_path / relative
            if not path.is_file():
                continue
            mtime = path.stat().st_mtime
            if latest is None or mtime > latest:
                latest = mtime
        git_time = self._git_latest_touch(scanned_files)
        if git_time is not None:
            if latest is None or git_time > latest:
                latest = git_time
        return latest

    def _latest_code_commit_time(self) -> float | None:
        if not (self._repo_path / ".git").exists():
            return None
        try:
            output = subprocess.run(
                ["git", "log", "-1", "--format=%ct"],
                cwd=self._repo_path,
                check=True,
                capture_output=True,
                text=True,
            )
            return float(output.stdout.strip())
        except (subprocess.CalledProcessError, ValueError):
            return None

    def _git_latest_touch(self, paths: list[str]) -> float | None:
        if not (self._repo_path / ".git").exists() or not paths:
            return None
        try:
            output = subprocess.run(
                ["git", "log", "-1", "--format=%ct", "--", *paths],
                cwd=self._repo_path,
                check=True,
                capture_output=True,
                text=True,
            )
            stripped = output.stdout.strip()
            if not stripped:
                return None
            return float(stripped)
        except (subprocess.CalledProcessError, ValueError):
            return None

    def _recency_grace_days(self) -> int:
        if not (self._repo_path / ".git").exists():
            return RECENCY_GRACE_QUIET_DAYS
        try:
            output = subprocess.run(
                [
                    "git",
                    "rev-list",
                    "--count",
                    f"--since={RECENCY_GRACE_ACTIVE_DAYS} days ago",
                    "HEAD",
                ],
                cwd=self._repo_path,
                check=True,
                capture_output=True,
                text=True,
            )
            count = int(output.stdout.strip())
            if count >= RECENCY_COMMIT_THRESHOLD:
                return RECENCY_GRACE_ACTIVE_DAYS
        except (subprocess.CalledProcessError, ValueError):
            pass
        return RECENCY_GRACE_QUIET_DAYS
