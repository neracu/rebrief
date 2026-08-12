from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout

from rebrief.core.confidence import parse_min_confidence
from rebrief.core.diff import DiffError, DiffScope, resolve_diff_scope
from rebrief.core.remote import RemoteCloneError, fetch_remote_head, temporary_clone
from rebrief.core.reporter import ReportPayload
from rebrief.core.scan import run_scan
from rebrief.webapp import WEB_CLONE_DEPTH
from rebrief.webapp.cache import ScanCache, cache_key
from rebrief.webapp.schemas import (
    RepoInfo,
    RiskCounts,
    ScanResponse,
    TechStackOut,
    TokenStatsOut,
)
from rebrief.webapp.urls import PublicUrlError, resolve_public_remote

DEFAULT_SCAN_TIMEOUT = 120.0
LS_REMOTE_TIMEOUT = 10.0


class ScanTimeoutError(Exception):
    """Raised when clone + scan exceeds SCAN_TIMEOUT_SECONDS."""


class WebScanError(Exception):
    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def scan_timeout_seconds() -> float:
    raw = os.environ.get("SCAN_TIMEOUT_SECONDS", str(int(DEFAULT_SCAN_TIMEOUT)))
    try:
        return max(1.0, float(raw))
    except ValueError:
        return DEFAULT_SCAN_TIMEOUT


def scan_public_repo(
    url: str,
    *,
    min_confidence: str = "medium",
    diff_ref: str | None = None,
    cache: ScanCache,
) -> ScanResponse:
    try:
        target = resolve_public_remote(url)
    except PublicUrlError as exc:
        raise WebScanError(str(exc), 400) from exc

    try:
        commit_sha = fetch_remote_head(target.clone_url, timeout=LS_REMOTE_TIMEOUT)
    except RemoteCloneError as exc:
        raise WebScanError(str(exc), 404) from exc

    key = cache_key(target.clone_url, commit_sha, min_confidence, diff_ref)
    cached = cache.get(key)
    if cached is not None:
        cached.cached = True
        return cached

    timeout = scan_timeout_seconds()

    def _run() -> ScanResponse:
        with temporary_clone(
            target,
            depth=WEB_CLONE_DEPTH,
            authenticated=False,
            timeout=timeout,
        ) as repo:
            confidence = parse_min_confidence(min_confidence)
            diff_scope: DiffScope | None = None
            if diff_ref is not None:
                diff_scope = resolve_diff_scope(repo, diff_ref)
            generator = run_scan(repo, confidence, diff_scope=diff_scope)
            return _to_response(
                clone_url=target.clone_url,
                display_name=target.display_name,
                commit_sha=commit_sha,
                markdown=generator.generate(),
                payload=generator.to_dict(),
                cached=False,
            )

    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            result = pool.submit(_run).result(timeout=timeout)
    except FuturesTimeout as exc:
        raise ScanTimeoutError("Scan timed out.") from exc
    except RemoteCloneError as exc:
        raise WebScanError(str(exc), 404) from exc
    except DiffError as exc:
        raise WebScanError(str(exc), 400) from exc
    except ValueError as exc:
        raise WebScanError(str(exc), 400) from exc

    cache.put(key, result)
    return result


def _to_response(
    *,
    clone_url: str,
    display_name: str,
    commit_sha: str,
    markdown: str,
    payload: ReportPayload,
    cached: bool,
) -> ScanResponse:
    risk_map = payload["risk_map"]
    stack = payload["tech_stack"]
    stats = payload["summary"]["token_stats"]
    return ScanResponse(
        cached=cached,
        repo=RepoInfo(
            url=clone_url,
            display_name=display_name,
            commit_sha=commit_sha,
        ),
        markdown=markdown,
        token_stats=TokenStatsOut(
            raw_codebase_tokens=stats["raw_codebase_tokens"],
            brief_tokens=stats["brief_tokens"],
            savings_percentage=stats["savings_percentage"],
            tokenizer=stats["tokenizer"],
        ),
        tech_stack=TechStackOut(
            languages=list(stack["languages"]),
            frameworks=list(stack["frameworks"]),
            manifests=list(stack["manifests"]),
        ),
        risks=RiskCounts(
            critical=len(risk_map["critical"]),
            warning=len(risk_map["warning"]),
            info=len(risk_map["info"]),
        ),
        mode=payload["mode"],
        diff_ref=payload["diff_ref"],
    )
