from __future__ import annotations

from pathlib import Path
from typing import TypedDict

RULE_FILES: tuple[str, ...] = (
    ".cursorrules",
    "CLAUDE.md",
    "AGENTS.md",
    ".claudecode",
    "README.md",
)
PREVIEW_LINE_COUNT = 10
FULL_CONTENT_LINE_LIMIT = 200
README_FILENAME = "README.md"


class RuleFileEntry(TypedDict):
    content: str
    lines_count: int


class RulesParser:
    def __init__(self, repo_path: str) -> None:
        self._repo_path = Path(repo_path)

    def parse(self) -> dict[str, RuleFileEntry]:
        result: dict[str, RuleFileEntry] = {}

        for canonical_name, path in self._find_rule_files().items():
            text = self._read_file(path)
            result[canonical_name] = self._build_entry(canonical_name, text)

        return result

    def _find_rule_files(self) -> dict[str, Path]:
        if not self._repo_path.is_dir():
            return {}

        root_files = {
            entry.name.casefold(): entry
            for entry in self._repo_path.iterdir()
            if entry.is_file()
        }

        found: dict[str, Path] = {}
        for canonical_name in RULE_FILES:
            path = root_files.get(canonical_name.casefold())
            if path is not None:
                found[canonical_name] = path

        return found

    def _read_file(self, path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return ""

    def _build_entry(self, filename: str, text: str) -> RuleFileEntry:
        lines = text.splitlines()
        lines_count = len(lines)

        if filename == README_FILENAME or lines_count >= FULL_CONTENT_LINE_LIMIT:
            content = "\n".join(lines[:PREVIEW_LINE_COUNT])
        else:
            content = text

        return {
            "content": content,
            "lines_count": lines_count,
        }
