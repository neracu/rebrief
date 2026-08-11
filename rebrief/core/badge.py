from __future__ import annotations

import re
from pathlib import Path
from typing import TypedDict

BADGE_LINK = "https://github.com/neracu/rebrief"
BADGE_START = "<!-- REBRIEF-BADGE:START -->"
BADGE_END = "<!-- REBRIEF-BADGE:END -->"
README_FILENAME = "README.md"

_H1_RE = re.compile(r"^#\s+.+$", re.MULTILINE)
_MARKER_BLOCK_RE = re.compile(
    re.escape(BADGE_START) + r".*?" + re.escape(BADGE_END),
    re.DOTALL,
)


class BadgeSnippets(TypedDict):
    badge_url: str
    badge_markdown: str
    badge_html: str


def build_badge(critical: int, warning: int, info: int) -> BadgeSnippets:
    """Build Shields.io badge snippets from filtered severity counts."""
    total = critical + warning + info

    if critical > 0:
        label = f"{critical} critical"
        color = "red"
    elif total > 0:
        label = f"{total} risks"
        color = "yellow"
    else:
        label = "clean"
        color = "brightgreen"

    encoded_label = label.replace(" ", "%20")
    badge_url = f"https://img.shields.io/badge/rebrief-{encoded_label}-{color}"
    badge_markdown = f"[![Rebrief]({badge_url})]({BADGE_LINK})"
    badge_html = f'<a href="{BADGE_LINK}"><img alt="Rebrief" src="{badge_url}"></a>'

    return {
        "badge_url": badge_url,
        "badge_markdown": badge_markdown,
        "badge_html": badge_html,
    }


def format_badge_block(badge_markdown: str) -> str:
    return f"{BADGE_START}\n{badge_markdown}\n{BADGE_END}"


def inject_badge_content(content: str, badge_markdown: str) -> str:
    """Replace or insert a REBRIEF badge marker block in README content."""
    block = format_badge_block(badge_markdown)

    if BADGE_START in content and BADGE_END in content:
        return _MARKER_BLOCK_RE.sub(block, content, count=1)

    match = _H1_RE.search(content)
    if match is not None:
        insert_at = match.end()
        return content[:insert_at] + "\n\n" + block + content[insert_at:]

    if content and not content.endswith("\n"):
        return block + "\n" + content
    return block + "\n" + content


def find_readme_path(repo_path: str | Path) -> Path | None:
    """Locate README.md under repo root (case-insensitive)."""
    root = Path(repo_path)
    if not root.is_dir():
        return None

    for entry in root.iterdir():
        if entry.is_file() and entry.name.casefold() == README_FILENAME.casefold():
            return entry
    return None


def inject_readme_badge(repo_path: str | Path, badge_markdown: str) -> Path:
    """
    Inject or update the badge block in the repository README.

    Creates README.md if none exists.
    Returns the path that was written.
    """
    root = Path(repo_path)
    readme = find_readme_path(root)
    if readme is None:
        readme = root / README_FILENAME
        content = ""
    else:
        content = readme.read_text(encoding="utf-8")

    updated = inject_badge_content(content, badge_markdown)
    readme.write_text(updated, encoding="utf-8")
    return readme
