from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_MODELS = {
    "anthropic": "anthropic/claude-3-5-sonnet",
    "openai": "openai/gpt-4o-mini",
    "gemini": "gemini/gemini-2.0-flash",
    "openrouter": "openrouter/openai/gpt-4o-mini",
    "ollama": "ollama/llama3",
}

ENV_KEYS = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}

DEFAULT_OLLAMA_URL = "http://localhost:11434"
PROVIDER_ORDER = ("anthropic", "openai", "gemini", "openrouter", "ollama")

MISSING_CREDENTIALS = (
    "No LLM credentials found. Set ANTHROPIC_API_KEY, OPENAI_API_KEY, "
    "GEMINI_API_KEY, OPENROUTER_API_KEY, or OLLAMA_BASE_URL, or pass --key / api_key."
)


class ChatError(Exception):
    """User-facing chat error with secrets stripped from the message."""

    def __init__(self, message: str, *, secrets: tuple[str, ...] = ()) -> None:
        super().__init__(redact_secrets(message, secrets))


def mask_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "****"
    return f"{value[:4]}****{value[-4:]}"


def redact_secrets(text: str, secrets: tuple[str, ...] | list[str] = ()) -> str:
    result = text
    for secret in secrets:
        if secret and secret in result:
            result = result.replace(secret, mask_secret(secret))
    return result


@dataclass(frozen=True)
class ResolvedAuth:
    provider: str
    model_id: str
    model: str
    api_key: str | None
    base_url: str | None

    def secrets(self) -> tuple[str, ...]:
        if self.api_key:
            return (self.api_key,)
        return ()


def parse_model(model: str) -> tuple[str, str]:
    raw = model.strip()
    if not raw:
        raise ChatError("Model name must not be empty.")
    if "/" in raw:
        provider, _, name = raw.partition("/")
        provider = provider.strip().lower()
        name = name.strip()
        if provider in {"google"}:
            provider = "gemini"
        if provider not in DEFAULT_MODELS:
            raise ChatError(
                f"Unsupported provider {provider!r}. "
                "Use anthropic/, openai/, gemini/, openrouter/, or ollama/."
            )
        if not name:
            raise ChatError("Model name must not be empty.")
        return provider, name
    lowered = raw.lower()
    if lowered.startswith("claude"):
        return "anthropic", raw
    if lowered.startswith("gpt") or lowered.startswith("o1") or lowered.startswith("o3"):
        return "openai", raw
    if lowered.startswith("gemini"):
        return "gemini", raw
    if lowered.startswith("llama") or lowered.startswith("mistral") or lowered.startswith("qwen"):
        return "ollama", raw
    raise ChatError(
        f"Cannot infer provider for {raw!r}. "
        "Use a prefixed name such as openai/gpt-4o-mini."
    )


def _env(name: str) -> str:
    return os.environ.get(name, "").strip()


def _ollama_configured() -> bool:
    return bool(_env("OLLAMA_BASE_URL"))


def default_model_from_env() -> str | None:
    if _env(ENV_KEYS["anthropic"]):
        return DEFAULT_MODELS["anthropic"]
    if _env(ENV_KEYS["openai"]):
        return DEFAULT_MODELS["openai"]
    if _env(ENV_KEYS["gemini"]):
        return DEFAULT_MODELS["gemini"]
    if _env(ENV_KEYS["openrouter"]):
        return DEFAULT_MODELS["openrouter"]
    if _ollama_configured():
        return DEFAULT_MODELS["ollama"]
    return None


def resolve_auth(
    model: str | None = None,
    api_key: str | None = None,
) -> ResolvedAuth:
    explicit_key = (api_key or "").strip() or None
    chosen = (model or "").strip() or default_model_from_env()
    if not chosen:
        if explicit_key:
            raise ChatError(
                "Pass --model / model when providing an API key without "
                "provider environment variables."
            )
        raise ChatError(MISSING_CREDENTIALS)

    provider, model_id = parse_model(chosen)
    full_name = f"{provider}/{model_id}"
    key = explicit_key
    base_url: str | None = None

    if provider == "ollama":
        base_url = _env("OLLAMA_BASE_URL") or DEFAULT_OLLAMA_URL
        return ResolvedAuth(
            provider=provider,
            model_id=model_id,
            model=full_name,
            api_key=key,
            base_url=base_url.rstrip("/"),
        )

    if key is None:
        key = _env(ENV_KEYS[provider]) or None
    if not key:
        env_name = ENV_KEYS[provider]
        raise ChatError(
            f"Missing API key for {provider}. Set {env_name} or pass --key / api_key."
        )
    return ResolvedAuth(
        provider=provider,
        model_id=model_id,
        model=full_name,
        api_key=key,
        base_url=None,
    )
