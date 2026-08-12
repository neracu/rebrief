from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

import pytest

from rebrief.chat.client import (
    MAX_HISTORY_MESSAGES,
    normalize_messages,
    stream_completion,
)
from rebrief.chat.credentials import ChatError, ResolvedAuth, mask_secret, parse_model, resolve_auth


def _auth(provider: str = "openai", key: str = "sk-test-secret-key") -> ResolvedAuth:
    return ResolvedAuth(
        provider=provider,
        model_id="gpt-4o-mini" if provider == "openai" else "claude-3-5-sonnet",
        model=f"{provider}/demo",
        api_key=key,
        base_url="http://localhost:11434" if provider == "ollama" else None,
    )


class FakeResponse:
    def __init__(self, lines: list[str], status_code: int = 200, text: str = "") -> None:
        self._lines = lines
        self.status_code = status_code
        self.text = text

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            import httpx

            request = httpx.Request("POST", "https://example.com")
            response = httpx.Response(self.status_code, text=self.text, request=request)
            raise httpx.HTTPStatusError("error", request=request, response=response)

    def iter_lines(self) -> Iterator[str]:
        yield from self._lines


class FakeClient:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []
        self.closed = False

    def stream(self, method: str, url: str, json: dict[str, Any] | None = None, headers: dict[str, str] | None = None):
        self.calls.append({"method": method, "url": url, "json": json, "headers": headers})

        @contextmanager
        def _ctx() -> Iterator[FakeResponse]:
            yield self.response

        return _ctx()

    def close(self) -> None:
        self.closed = True


def test_normalize_strips_system_and_caps_history() -> None:
    messages = [{"role": "system", "content": "ignore me"}]
    messages.extend({"role": "user", "content": f"q{i}"} for i in range(30))
    cleaned = normalize_messages(messages)
    assert all(item["role"] != "system" for item in cleaned)
    assert len(cleaned) == MAX_HISTORY_MESSAGES
    assert cleaned[0]["content"] == "q10"


def test_openai_stream_injects_system_prompt() -> None:
    lines = [
        'data: {"choices":[{"delta":{"content":"Hello"}}]}',
        'data: {"choices":[{"delta":{"content":" world"}}]}',
        "data: [DONE]",
    ]
    client = FakeClient(FakeResponse(lines))
    chunks = list(
        stream_completion(
            auth=_auth("openai"),
            system_prompt="SYS",
            messages=[{"role": "user", "content": "hi"}, {"role": "system", "content": "nope"}],
            http_client=client,
        )
    )
    assert "".join(chunks) == "Hello world"
    payload = client.calls[0]["json"]
    assert payload["messages"][0] == {"role": "system", "content": "SYS"}
    assert payload["messages"][1] == {"role": "user", "content": "hi"}
    assert all(item["role"] != "system" or item["content"] == "SYS" for item in payload["messages"])


def test_anthropic_stream_uses_system_field() -> None:
    lines = [
        'event: content_block_delta',
        'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"Hi"}}',
    ]
    client = FakeClient(FakeResponse(lines))
    chunks = list(
        stream_completion(
            auth=_auth("anthropic", "sk-ant-secret-value"),
            system_prompt="SYS",
            messages=[{"role": "user", "content": "q"}],
            http_client=client,
        )
    )
    assert chunks == ["Hi"]
    call = client.calls[0]
    assert call["url"].endswith("/v1/messages")
    assert call["json"]["system"] == "SYS"
    assert call["headers"]["x-api-key"] == "sk-ant-secret-value"


def test_ollama_uses_local_openai_compatible_url() -> None:
    client = FakeClient(FakeResponse(['data: {"choices":[{"delta":{"content":"ok"}}]}']))
    auth = ResolvedAuth(
        provider="ollama",
        model_id="llama3",
        model="ollama/llama3",
        api_key=None,
        base_url="http://localhost:11434",
    )
    chunks = list(
        stream_completion(
            auth=auth,
            system_prompt="SYS",
            messages=[{"role": "user", "content": "q"}],
            http_client=client,
        )
    )
    assert chunks == ["ok"]
    assert client.calls[0]["url"] == "http://localhost:11434/v1/chat/completions"


def test_openrouter_keeps_nested_model_id() -> None:
    provider, model_id = parse_model("openrouter/anthropic/claude-3.5-sonnet")
    assert provider == "openrouter"
    assert model_id == "anthropic/claude-3.5-sonnet"
    client = FakeClient(FakeResponse(['data: {"choices":[{"delta":{"content":"or"}}]}']))
    auth = ResolvedAuth(
        provider="openrouter",
        model_id=model_id,
        model="openrouter/anthropic/claude-3.5-sonnet",
        api_key="sk-or-test-key",
        base_url=None,
    )
    chunks = list(
        stream_completion(
            auth=auth,
            system_prompt="SYS",
            messages=[{"role": "user", "content": "q"}],
            http_client=client,
        )
    )
    assert chunks == ["or"]
    call = client.calls[0]
    assert call["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert call["json"]["model"] == "anthropic/claude-3.5-sonnet"
    assert call["headers"]["Authorization"] == "Bearer sk-or-test-key"


def test_resolve_auth_openrouter(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "OLLAMA_BASE_URL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-env-key-1234")
    auth = resolve_auth()
    assert auth.provider == "openrouter"
    assert auth.model == "openrouter/openai/gpt-4o-mini"
    assert auth.model_id == "openai/gpt-4o-mini"
    assert auth.api_key == "sk-or-env-key-1234"


def test_http_error_masks_api_key() -> None:
    secret = "sk-live-super-secret-key"
    client = FakeClient(FakeResponse([], status_code=401, text=f"invalid {secret}"))
    with pytest.raises(ChatError) as exc_info:
        list(
            stream_completion(
                auth=_auth("openai", secret),
                system_prompt="SYS",
                messages=[{"role": "user", "content": "q"}],
                http_client=client,
            )
        )
    message = str(exc_info.value)
    assert secret not in message
    assert mask_secret(secret) in message


def test_resolve_auth_prefers_anthropic(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-env-key-1234")
    auth = resolve_auth()
    assert auth.model == "anthropic/claude-3-5-sonnet"
    assert auth.api_key == "sk-ant-env-key-1234"


def test_explicit_key_overrides_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-env-should-not-use")
    auth = resolve_auth(model="openai/gpt-4o-mini", api_key="sk-explicit-override")
    assert auth.api_key == "sk-explicit-override"


def test_missing_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "GEMINI_API_KEY",
        "OPENROUTER_API_KEY",
        "OLLAMA_BASE_URL",
    ):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(ChatError, match="No LLM credentials"):
        resolve_auth()
