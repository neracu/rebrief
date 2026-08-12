from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class ScanRequest(BaseModel):
    url: str = Field(min_length=1)
    min_confidence: Literal["high", "medium", "low"] = "medium"
    diff_ref: str | None = None

    @field_validator("url")
    @classmethod
    def strip_url(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("url must not be empty")
        return stripped

    @field_validator("diff_ref")
    @classmethod
    def empty_diff_ref(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class RepoInfo(BaseModel):
    url: str
    display_name: str
    commit_sha: str


class TokenStatsOut(BaseModel):
    raw_codebase_tokens: int
    brief_tokens: int
    savings_percentage: float
    tokenizer: str


class TechStackOut(BaseModel):
    languages: list[str]
    frameworks: list[str]
    manifests: list[str]


class RiskCounts(BaseModel):
    critical: int
    warning: int
    info: int


class ScanResponse(BaseModel):
    cached: bool
    repo: RepoInfo
    markdown: str
    token_stats: TokenStatsOut
    tech_stack: TechStackOut
    risks: RiskCounts
    mode: Literal["full", "incremental"]
    diff_ref: str | None


class ChatMessageIn(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str = Field(min_length=1)

    @field_validator("content")
    @classmethod
    def strip_content(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("content must not be empty")
        return stripped


class ChatRequest(BaseModel):
    repo_url: str = Field(min_length=1)
    messages: list[ChatMessageIn]
    api_key: str | None = None
    model: str | None = None

    @field_validator("repo_url")
    @classmethod
    def strip_repo_url(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("repo_url must not be empty")
        return stripped

    @field_validator("api_key")
    @classmethod
    def empty_api_key(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @field_validator("model")
    @classmethod
    def empty_model(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None
