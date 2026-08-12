from __future__ import annotations

import os

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from rebrief.webapp.cache import build_cache
from rebrief.webapp.rate_limit import build_limiter, scan_rate_limit
from rebrief.webapp.schemas import ScanRequest, ScanResponse
from rebrief.webapp.service import ScanTimeoutError, WebScanError, scan_public_repo

STATIC_DIR = Path(__file__).resolve().parent / "static"
INDEX_HTML = STATIC_DIR / "index.html"


def browser_url(host: str, port: int) -> str:
    """URL to open in a local browser for ``rebrief serve``."""
    browse_host = "127.0.0.1" if host in {"0.0.0.0", "::", "[::]"} else host
    return f"http://{browse_host}:{port}/"


def _cors_origins() -> list[str]:
    raw = os.environ.get("FRONTEND_ORIGIN", "http://localhost:3000")
    origins = [item.strip() for item in raw.split(",") if item.strip()]
    return origins or ["http://localhost:3000"]


def create_app() -> FastAPI:
    app = FastAPI(title="rebrief", docs_url=None, redoc_url=None)
    limiter = build_limiter()
    app.state.limiter = limiter
    app.state.scan_cache = build_cache()
    app.add_middleware(SlowAPIMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins(),
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type"],
    )

    @app.exception_handler(RateLimitExceeded)
    async def rate_limit_handler(
        request: Request, exc: RateLimitExceeded
    ) -> JSONResponse:
        return JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded: 10 scans per minute per IP."},
        )

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/scan", response_model=ScanResponse)
    @limiter.limit(scan_rate_limit())
    def scan(request: Request, body: ScanRequest, response: Response) -> ScanResponse:
        try:
            return scan_public_repo(
                body.url,
                min_confidence=body.min_confidence,
                diff_ref=body.diff_ref,
                cache=request.app.state.scan_cache,
            )
        except WebScanError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
        except ScanTimeoutError as exc:
            raise HTTPException(status_code=504, detail=str(exc)) from exc

    @app.get("/")
    def ui_index() -> FileResponse:
        return FileResponse(INDEX_HTML, media_type="text/html; charset=utf-8")

    return app


app = create_app()
