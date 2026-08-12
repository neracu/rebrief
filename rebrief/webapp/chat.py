from __future__ import annotations

import json
from collections.abc import Iterator

from rebrief.chat.client import stream_completion
from rebrief.chat.context import format_system_prompt
from rebrief.chat.credentials import ChatError, resolve_auth
from rebrief.webapp.schemas import ChatRequest


def iter_chat_sse(body: ChatRequest, markdown: str) -> Iterator[str]:
    try:
        auth = resolve_auth(model=body.model, api_key=body.api_key)
    except ChatError as exc:
        yield _sse({"error": str(exc)})
        return

    system_prompt = format_system_prompt(markdown)
    history = [{"role": item.role, "content": item.content} for item in body.messages]
    try:
        for delta in stream_completion(
            auth=auth,
            system_prompt=system_prompt,
            messages=history,
        ):
            yield _sse({"delta": delta})
        yield _sse({"done": True})
    except ChatError as exc:
        yield _sse({"error": str(exc)})


def _sse(payload: dict[str, object]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
