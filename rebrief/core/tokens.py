from __future__ import annotations

import os
from pathlib import Path
from typing import Sequence, TypedDict

from rebrief.core.ignore import IgnoreMatcher

ENCODING_NAME = "cl100k_base"
FALLBACK_TOKENIZER = "char_ratio"
CHAR_RATIO = 4
MAX_FILE_BYTES = 10 * 1024 * 1024
BINARY_PEEK_BYTES = 8192
SKIP_REPORT_NAMES = frozenset({"REBRIEF.md", "REBRIEF.json", "REBRIEF.xml", "REBRIEF.html"})

BINARY_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".pyc",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".zip",
        ".exe",
        ".dll",
        ".so",
        ".dylib",
        ".woff",
        ".woff2",
        ".ico",
        ".pdf",
        ".db",
    }
)

_encoding = None
_encoding_failed = False


def reset_tokenizer_cache() -> None:
    """Clear cached encoder state (used by tests)."""
    global _encoding, _encoding_failed
    _encoding = None
    _encoding_failed = False


class TokenStats(TypedDict):
    raw_codebase_tokens: int
    brief_tokens: int
    savings_percentage: float
    tokenizer: str


def active_tokenizer() -> str:
    encoding = _get_encoding()
    return ENCODING_NAME if encoding is not None else FALLBACK_TOKENIZER


def _get_encoding():
    global _encoding, _encoding_failed
    if _encoding_failed:
        return None
    if _encoding is not None:
        return _encoding
    try:
        import tiktoken

        _encoding = tiktoken.get_encoding(ENCODING_NAME)
        return _encoding
    except Exception:
        _encoding_failed = True
        return None


def _approx_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, len(text) // CHAR_RATIO)


def count_tokens(text: str) -> int:
    """Count tokens using cl100k_base, or a character-ratio heuristic."""
    if not text:
        return 0
    encoding = _get_encoding()
    if encoding is None:
        return _approx_tokens(text)
    try:
        return len(encoding.encode(text, disallowed_special=()))
    except Exception:
        return _approx_tokens(text)


def savings_percentage(raw_tokens: int, brief_tokens: int) -> float:
    if raw_tokens <= 0:
        return 0.0
    return round((1 - brief_tokens / raw_tokens) * 100, 2)


def empty_token_stats() -> TokenStats:
    return {
        "raw_codebase_tokens": 0,
        "brief_tokens": 0,
        "savings_percentage": 0.0,
        "tokenizer": active_tokenizer(),
    }


def complete_token_stats(raw_tokens: int, brief_tokens: int, tokenizer: str) -> TokenStats:
    return {
        "raw_codebase_tokens": raw_tokens,
        "brief_tokens": brief_tokens,
        "savings_percentage": savings_percentage(raw_tokens, brief_tokens),
        "tokenizer": tokenizer,
    }


def format_raw_cli(count: int) -> str:
    return f"~{count:,} tokens"


def format_brief_cli(count: int) -> str:
    return f"{count:,} tokens"


def format_savings_cli(percentage: float) -> str:
    return f"{percentage:.1f}% token savings"


def format_compact_count(count: int) -> str:
    if count >= 1_000_000:
        value = count / 1_000_000
        text = f"{value:.1f}".rstrip("0").rstrip(".")
        return f"{text}M"
    if count >= 1_000:
        value = count / 1_000
        text = f"{value:.1f}".rstrip("0").rstrip(".")
        return f"{text}k"
    return str(count)


def format_savings_footnote(stats: TokenStats) -> str:
    brief = stats["brief_tokens"]
    raw = format_compact_count(stats["raw_codebase_tokens"])
    pct = f"{stats['savings_percentage']:.1f}"
    return (
        f"> 💡 **Token Savings:** `REBRIEF.md` uses **{brief:,} tokens** "
        f"instead of **{raw} raw tokens** (**{pct}% reduction**)."
    )


def count_repo_tokens(
    repo_path: str | Path,
    paths: Sequence[str] | None = None,
) -> TokenStats:
    """Sum tokens of unignored text files. ``brief_tokens`` stays 0 until the report is built."""
    repo = Path(repo_path)
    matcher = IgnoreMatcher(repo)
    total = 0

    for file_path in _iter_text_files(repo, matcher, paths):
        text = _read_text_file(file_path)
        if text is None:
            continue
        total += count_tokens(text)

    return complete_token_stats(total, 0, active_tokenizer())


def _iter_text_files(
    repo: Path,
    matcher: IgnoreMatcher,
    paths: Sequence[str] | None,
):
    if paths is not None:
        for relative in sorted(paths):
            file_path = repo / relative.replace("\\", "/")
            if not file_path.is_file():
                continue
            posix = file_path.relative_to(repo).as_posix()
            if matcher.is_ignored(posix, is_dir=False):
                continue
            if file_path.name in SKIP_REPORT_NAMES:
                continue
            yield file_path
        return

    for root, dirs, files in os.walk(repo):
        root_path = Path(root)
        relative_root = root_path.relative_to(repo).as_posix()
        if relative_root == ".":
            relative_root = ""

        dirs[:] = sorted(
            directory
            for directory in dirs
            if not matcher.should_prune_dir(directory, relative_root)
        )

        for filename in sorted(files):
            if filename in SKIP_REPORT_NAMES:
                continue
            file_path = root_path / filename
            relative_file = file_path.relative_to(repo).as_posix()
            if matcher.is_ignored(relative_file, is_dir=False):
                continue
            yield file_path


def _read_text_file(path: Path) -> str | None:
    if path.suffix.lower() in BINARY_EXTENSIONS:
        return None
    try:
        size = path.stat().st_size
    except OSError:
        return None
    if size > MAX_FILE_BYTES:
        return None
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if b"\x00" in data[:BINARY_PEEK_BYTES]:
        return None
    return data.decode("utf-8", errors="ignore")
