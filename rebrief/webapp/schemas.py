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
