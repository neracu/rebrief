from __future__ import annotations

import re
import subprocess
import time
from pathlib import Path
from typing import Literal, TypedDict

from rebrief.core.confidence import Confidence
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

# Rival families: documented keyword -> family id
STACK_KEYWORDS: dict[str, str] = {
    "vue": "frontend",
    "vue 2": "frontend",
    "vue 3": "frontend",
    "react": "frontend",
    "angular": "frontend",
    "svelte": "frontend",
    "next.js": "frontend",
    "nextjs": "frontend",
    "nuxt": "frontend",
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

# Map detected stack signals to families / display names
DETECTED_STACK_SIGNALS: dict[str, tuple[str, str]] = {
    # (family, display_name)
    "react": ("frontend", "React"),
    "vue": ("frontend", "Vue"),
    "@angular/core": ("frontend", "Angular"),
    "angular": ("frontend", "Angular"),
    "svelte": ("frontend", "Svelte"),
    "next": ("frontend", "Next.js"),
    "nuxt": ("frontend", "Nuxt.js"),
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

LANGUAGE_TO_FAMILY: dict[str, str] = {
    "JavaScript/TypeScript": "language",
    "Python": "language",
    "Go": "language",
    "Rust": "language",
    "Java": "language",
    "Kotlin": "language",
    "PHP": "language",
    "Ruby": "language",
}

LANGUAGE_DISPLAY: dict[str, str] = {
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
ENV_BACKTICK_RE = re.compile(r"`([A-Z][A-Z0-9_]{2,})`")

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
        "http",
        "https",
        "www",
        "example",
        "com",
        "org",
        "io",
        "npm",
        "github",
    }
)

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


class FreshnessParser:
    def __init__(self, repo_path: str, stack: StackResult) -> None:
        self._repo_path = Path(repo_path)
        self._stack = stack

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
                if path.is_file():
                    key = path.relative_to(self._repo_path).as_posix()
                    found[key] = self._read_file(path)

        cursor_rules = self._repo_path / CURSOR_RULES_DIR
        if cursor_rules.is_dir():
            for path in sorted(cursor_rules.rglob("*")):
                if path.is_file() and path.suffix.casefold() == MDC_SUFFIX:
                    key = path.relative_to(self._repo_path).as_posix()
                    found[key] = self._read_file(path)

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
        detected_families, detected_displays = self._detected_stack_signals()
        documented_keywords = self._find_documented_stack_keywords(doc_files)

        conflicts = 0
        for source, keyword, family, display in documented_keywords:
            if family == "language":
                if not self._language_documented_matches(display, detected_displays):
                    conflicts += 1
                    actual = self._format_detected_for_family(
                        family, detected_families, detected_displays
                    )
                    items.append(
                        {
                            "severity": "warning",
                            "confidence": Confidence.HIGH.value,
                            "kind": "stack",
                            "source": source,
                            "message": (
                                f'{source} references "{display}" but project '
                                f"depends on {actual}"
                            ),
                        }
                    )
                continue

            family_detected = detected_families.get(family)
            if family_detected is None:
                continue
            if family_detected.lower() != display.lower():
                conflicts += 1
                items.append(
                    {
                        "severity": "warning",
                        "confidence": Confidence.HIGH.value,
                        "kind": "stack",
                        "source": source,
                        "message": (
                            f'{source} references "{display}" but project '
                            f'depends on "{family_detected}"'
                        ),
                    }
                )

        return conflicts, len(documented_keywords)

    def _detected_stack_signals(self) -> tuple[dict[str, str], set[str]]:
        families: dict[str, str] = {}
        displays: set[str] = set()

        for framework in self._stack["frameworks"]:
            display = FRAMEWORK_TO_DISPLAY.get(framework, framework)
            displays.add(display)
            for key, (family, mapped_display) in DETECTED_STACK_SIGNALS.items():
                if mapped_display.lower() == framework.lower():
                    families[family] = display
                    break
            else:
                name_lower = framework.lower()
                for keyword, (family, mapped) in DETECTED_STACK_SIGNALS.items():
                    if keyword in name_lower or name_lower in keyword:
                        families[family] = display
                        break

        deps_lower = " ".join(dep.lower() for dep in self._stack["dependencies"])
        for signal, (family, display) in DETECTED_STACK_SIGNALS.items():
            if signal in deps_lower and family not in families:
                families[family] = display
                displays.add(display)

        for language in self._stack["languages"]:
            display = LANGUAGE_DISPLAY.get(language, language)
            displays.add(display)
            family = LANGUAGE_TO_FAMILY.get(language)
            if family:
                families.setdefault(family, display)

        return families, displays

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
                display = keyword.title() if keyword != "go" else "Go"
                if keyword == "vue 2":
                    display = "Vue"
                elif keyword == "vue 3":
                    display = "Vue"
                elif keyword == "nextjs":
                    display = "Next.js"
                elif keyword == "golang":
                    display = "Go"
                elif keyword == "typescript":
                    display = "TypeScript"
                elif keyword == "javascript":
                    display = "JavaScript"
                hits.append((source, keyword, family, display))

        return hits

    def _language_documented_matches(
        self, documented: str, detected_displays: set[str]
    ) -> bool:
        doc_lower = documented.lower()
        for display in detected_displays:
            if doc_lower in display.lower() or display.lower() in doc_lower:
                return True
        langs = {lang.lower() for lang in self._stack["languages"]}
        if doc_lower in langs:
            return True
        if doc_lower == "javascript" and "javascript/typescript" in langs:
            return True
        if doc_lower == "typescript" and "javascript/typescript" in langs:
            return True
        if doc_lower == "golang" and "go" in langs:
            return True
        return not langs

    def _format_detected_for_family(
        self,
        family: str,
        detected_families: dict[str, str],
        detected_displays: set[str],
    ) -> str:
        if family in detected_families:
            return f'"{detected_families[family]}"'
        if detected_displays:
            return ", ".join(f'"{name}"' for name in sorted(detected_displays))
        return "a different stack"

    def _detect_path_drift(
        self,
        doc_files: dict[str, str],
        items: list[DocDriftItem],
    ) -> tuple[int, int]:
        valid = 0
        total = 0
        seen_missing: set[tuple[str, str]] = set()

        for source, text in doc_files.items():
            for raw_path in self._extract_paths(text):
                normalized = self._normalize_path(raw_path)
                if normalized is None:
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

    def _extract_paths(self, text: str) -> list[str]:
        paths: list[str] = []
        for match in PATH_BACKTICK_RE.finditer(text):
            paths.append(match.group(1).strip())
        for match in PATH_LINK_RE.finditer(text):
            paths.append(match.group(1).strip())
        for match in PATH_SLASH_RE.finditer(text):
            paths.append(match.group(0).strip())
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
        candidate = candidate.lstrip("./")
        if not candidate or candidate.endswith((".png", ".jpg", ".gif", ".svg", ".ico")):
            return None
        if "/" not in candidate and candidate.casefold() in GENERIC_PATH_WORDS:
            return None
        if candidate.count("/") == 0 and candidate.casefold() in GENERIC_PATH_WORDS:
            return None
        parts = [part for part in candidate.split("/") if part and part != "."]
        if not parts:
            return None
        if len(parts) == 1 and parts[0].casefold() in GENERIC_PATH_WORDS:
            return None
        return "/".join(parts)

    def _path_exists(self, relative: str) -> bool:
        target = self._repo_path / relative
        return target.exists()

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
        for pattern in (ENV_PROCESS_RE, ENV_DOLLAR_RE, ENV_BACKTICK_RE):
            for match in pattern.finditer(combined):
                keys.add(match.group(1))
        return keys

    def _compute_recency_ratio(self, scanned_files: list[str]) -> float:
        now = time.time()
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
        # Linear decay from grace to 2x grace
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
