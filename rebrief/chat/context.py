from __future__ import annotations

import json
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path

from rebrief.chat.credentials import ChatError
from rebrief.core.confidence import Confidence
from rebrief.core.remote import RemoteCloneError, resolve_remote_target, temporary_clone
from rebrief.core.scan import run_scan
from rebrief.core.tokens import count_tokens

StatusFactory = Callable[[str], AbstractContextManager[object]]

SYSTEM_PROMPT_TEMPLATE = """You are Rebrief Assistant, an expert codebase analyst.
Below is the pre-scanned architectural context, hotspots, risk map, and stack analysis for the repository:

--- BEGIN REBRIEF CONTEXT ---
{rebrief_markdown_content}
--- END REBRIEF CONTEXT ---

Answer the user's questions strictly based on this architectural context, risk map, and code hotspots. Be concise, technical, and accurate.
"""

ALLOWED_SUFFIXES = {".md", ".json"}


@dataclass(frozen=True)
class ChatContext:
    content: str
    source: str
    system_prompt: str
    token_count: int


def format_system_prompt(rebrief_markdown_content: str) -> str:
    return SYSTEM_PROMPT_TEMPLATE.replace(
        "{rebrief_markdown_content}",
        rebrief_markdown_content.rstrip(),
    )


def load_report_file(path: str | Path) -> ChatContext:
    report = Path(path).expanduser()
    try:
        report = report.resolve()
    except OSError as exc:
        raise ChatError(f"Cannot read report file: {path}") from exc
    if not report.is_file():
        raise ChatError(f"Report not found: {path}")
    suffix = report.suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise ChatError("Chat context must be a REBRIEF.md or REBRIEF.json file.")
    try:
        text = report.read_text(encoding="utf-8")
    except OSError as exc:
        raise ChatError(f"Cannot read report file: {report}") from exc
    if suffix == ".json":
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ChatError(f"Invalid REBRIEF JSON: {report}") from exc
        content = json.dumps(payload, indent=2, ensure_ascii=False)
    else:
        content = text
    return _build_context(content, str(report))


def load_chat_context(
    target: str = ".",
    report_file: str | Path | None = None,
    *,
    status: StatusFactory | None = None,
    min_confidence: Confidence = Confidence.MEDIUM,
) -> ChatContext:
    if report_file is not None:
        return load_report_file(report_file)

    existing = find_existing_report(target)
    if existing is not None:
        return load_report_file(existing)

    return _scan_target(target, status=status, min_confidence=min_confidence)


def _build_context(content: str, source: str) -> ChatContext:
    prompt = format_system_prompt(content)
    return ChatContext(
        content=content,
        source=source,
        system_prompt=prompt,
        token_count=count_tokens(prompt),
    )


def find_existing_report(target: str) -> Path | None:
    roots: list[Path] = []
    local = Path(target)
    if local.is_dir():
        roots.append(local.resolve())
    cwd = Path.cwd()
    if cwd not in roots:
        roots.append(cwd)
    for root in roots:
        markdown = root / "REBRIEF.md"
        if markdown.is_file():
            return markdown
        payload = root / "REBRIEF.json"
        if payload.is_file():
            return payload
    return None


def _scan_target(
    target: str,
    *,
    status: StatusFactory | None,
    min_confidence: Confidence,
) -> ChatContext:
    remote = resolve_remote_target(target)
    if remote is not None:
        try:
            with temporary_clone(remote) as repo:
                generator = run_scan(repo, min_confidence, status=status)
                return _build_context(generator.generate(), "live scan")
        except RemoteCloneError as exc:
            raise ChatError(str(exc)) from exc

    repo = Path(target).expanduser()
    try:
        repo = repo.resolve()
    except OSError as exc:
        raise ChatError(f"Path does not exist or is not a directory: {target}") from exc
    if not repo.is_dir():
        raise ChatError(f"Path does not exist or is not a directory: {target}")
    generator = run_scan(repo, min_confidence, status=status)
    return _build_context(generator.generate(), "live scan")
