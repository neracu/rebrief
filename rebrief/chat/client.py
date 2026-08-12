from __future__ import annotations

import json
from collections.abc import Iterator, Sequence
from typing import Any

from rebrief.chat.credentials import ChatError, ResolvedAuth, redact_secrets

MAX_HISTORY_MESSAGES = 20
MAX_OUTPUT_TOKENS = 4096

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
OPENAI_URL = "https://api.openai.com/v1/chat/completions"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "{model}:streamGenerateContent"
)


def normalize_messages(
    messages: Sequence[dict[str, str]],
    *,
    limit: int = MAX_HISTORY_MESSAGES,
) -> list[dict[str, str]]:
    cleaned: list[dict[str, str]] = []
    for item in messages:
        role = (item.get("role") or "").strip().lower()
        content = item.get("content") or ""
        if role == "system":
            continue
        if role not in {"user", "assistant"}:
            continue
        if not str(content).strip():
            continue
        cleaned.append({"role": role, "content": str(content)})
    if len(cleaned) > limit:
        cleaned = cleaned[-limit:]
    return cleaned


def stream_completion(
    *,
    auth: ResolvedAuth,
    system_prompt: str,
    messages: Sequence[dict[str, str]],
    http_client: Any | None = None,
) -> Iterator[str]:
    try:
        import httpx
    except ImportError as exc:
        from rebrief.chat import CHAT_EXTRA_HINT

        raise ChatError(CHAT_EXTRA_HINT) from exc

    history = normalize_messages(messages)
    own_client = http_client is None
    client = http_client or httpx.Client(timeout=120.0)
    secrets = auth.secrets()
    try:
        url, headers, payload = _build_request(auth, system_prompt, history)
        with client.stream("POST", url, json=payload, headers=headers) as response:
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                body = exc.response.text if exc.response is not None else str(exc)
                raise ChatError(
                    f"LLM request failed ({exc.response.status_code}): {body}",
                    secrets=secrets,
                ) from exc
            yield from _iter_provider_deltas(auth.provider, response)
    except ChatError:
        raise
    except Exception as exc:
        raise ChatError(redact_secrets(str(exc), secrets), secrets=secrets) from exc
    finally:
        if own_client:
            client.close()


def _build_request(
    auth: ResolvedAuth,
    system_prompt: str,
    history: list[dict[str, str]],
) -> tuple[str, dict[str, str], dict[str, Any]]:
    if auth.provider == "anthropic":
        return (
            ANTHROPIC_URL,
            {
                "x-api-key": auth.api_key or "",
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            {
                "model": auth.model_id,
                "max_tokens": MAX_OUTPUT_TOKENS,
                "system": system_prompt,
                "messages": history,
                "stream": True,
            },
        )
    if auth.provider in {"openai", "ollama", "openrouter"}:
        url = OPENAI_URL
        headers = {"content-type": "application/json"}
        if auth.provider == "ollama":
            base = (auth.base_url or "http://localhost:11434").rstrip("/")
            url = f"{base}/v1/chat/completions"
            if auth.api_key:
                headers["Authorization"] = f"Bearer {auth.api_key}"
        elif auth.provider == "openrouter":
            url = OPENROUTER_URL
            headers["Authorization"] = f"Bearer {auth.api_key or ''}"
            headers["HTTP-Referer"] = "https://github.com/neracu/rebrief"
            headers["X-Title"] = "rebrief"
        else:
            headers["Authorization"] = f"Bearer {auth.api_key or ''}"
        return (
            url,
            headers,
            {
                "model": auth.model_id,
                "messages": [{"role": "system", "content": system_prompt}, *history],
                "stream": True,
                "max_tokens": MAX_OUTPUT_TOKENS,
            },
        )
    if auth.provider == "gemini":
        url = gemini_stream_url(auth.model_id, auth.api_key or "")
        return (
            url,
            {"content-type": "application/json"},
            {
                "system_instruction": {"parts": [{"text": system_prompt}]},
                "contents": _gemini_contents(history),
                "generationConfig": {"maxOutputTokens": MAX_OUTPUT_TOKENS},
            },
        )
    raise ChatError(f"Unsupported provider: {auth.provider}")


def _gemini_contents(history: list[dict[str, str]]) -> list[dict[str, Any]]:
    contents: list[dict[str, Any]] = []
    for item in history:
        role = "user" if item["role"] == "user" else "model"
        contents.append({"role": role, "parts": [{"text": item["content"]}]})
    if not contents:
        contents.append({"role": "user", "parts": [{"text": "Hello"}]})
    return contents


def _iter_provider_deltas(provider: str, response: Any) -> Iterator[str]:
    for data in _iter_sse_data(response):
        try:
            payload = json.loads(data)
        except json.JSONDecodeError:
            continue
        delta = _extract_delta(provider, payload)
        if delta:
            yield delta


def _extract_delta(provider: str, payload: dict[str, Any]) -> str:
    if provider == "anthropic":
        if payload.get("type") != "content_block_delta":
            return ""
        delta = payload.get("delta") or {}
        return str(delta.get("text") or "")
    if provider in {"openai", "ollama", "openrouter"}:
        choices = payload.get("choices") or []
        if not choices:
            return ""
        delta = choices[0].get("delta") or {}
        return str(delta.get("content") or "")
    if provider == "gemini":
        candidates = payload.get("candidates") or []
        if not candidates:
            return ""
        parts = ((candidates[0].get("content") or {}).get("parts")) or []
        texts = [str(part.get("text") or "") for part in parts]
        return "".join(texts)
    return ""


def _iter_sse_data(response: Any) -> Iterator[str]:
    for raw in response.iter_lines():
        if raw is None:
            continue
        line = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else str(raw)
        line = line.strip()
        if not line or line.startswith(":"):
            continue
        if line.startswith("event:"):
            continue
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if data == "[DONE]":
            return
        yield data


def gemini_stream_url(model_id: str, api_key: str) -> str:
    from urllib.parse import urlencode

    base = GEMINI_URL.format(model=model_id)
    return f"{base}?{urlencode({'alt': 'sse', 'key': api_key})}"
