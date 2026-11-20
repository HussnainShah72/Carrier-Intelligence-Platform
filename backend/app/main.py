"""
Career Intelligence Platform - FastAPI application.

Run from the `backend` directory:
    uvicorn app.main:app --reload --port 8000

Interactive API docs: http://127.0.0.1:8000/docs
"""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.db import init_db
from app.core.errors import AppError
from app.core.logging_setup import configure_logging, get_logger

configure_logging()
log = get_logger(__name__)

API_PREFIX = "/api"


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Start-up and shutdown."""
    log.info("=" * 72)
    log.info("Starting %s", settings.app_name)
    init_db()

    from app.services.llm.client import get_llm

    client = get_llm()
    log.info("LLM provider: %s (model: %s, fast: %s)",
             client.provider, client.model, settings.fast_model)
    if client.is_offline:
        log.warning(
            "No language model is configured - the deterministic OFFLINE engine will be used. "
            "Set LLM_PROVIDER in backend/.env for full quality."
        )

    from app.services.speech import stt, tts

    log.info("Speech recognition: faster-whisper installed=%s enabled=%s model=%s",
             stt.is_available(), settings.stt_enabled, settings.stt_model_size)
    log.info("Text-to-speech: active engine=%s piper_voices=%d",
             tts.active_engine(), sum(1 for v in tts.list_piper_voices() if v["ready"]))
    log.info("Job sources: %d configured, scraping enabled=%s",
             len(__import__("app.services.jobs.sources", fromlist=["ALL_SOURCES"]).ALL_SOURCES),
             settings.scrape_enabled)
    log.info("API ready on %s (docs at /docs)", API_PREFIX)
    log.info("=" * 72)

    yield

    log.info("Shutting down %s", settings.app_name)


app = FastAPI(
    title=settings.app_name,
    description=(
        "Backend for the Career Intelligence Platform: CV parsing, live job-posting "
        "collection, LLM role requirement generation, skill gap analysis, CV improvement, "
        "a structured voice mock interview with fully local speech, rubric-based scoring, "
        "and performance measurement."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["X-TTS-Engine", "X-TTS-Voice", "X-TTS-Processing-Ms", "X-TTS-Audio-Seconds"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Request logging with duration; keeps the SSE streams out of the noise."""
    started = time.perf_counter()
    response = await call_next(request)
    elapsed = (time.perf_counter() - started) * 1000

    if request.url.path.startswith(API_PREFIX) and not request.url.path.endswith(("/health", "/dashboard")):
        log.info("%s %s -> %s in %.0fms", request.method, request.url.path, response.status_code, elapsed)
    response.headers["X-Response-Time-Ms"] = f"{elapsed:.1f}"
    return response


# ---------------------------------------------------------------------------
# Error handling: a stable shape, and never an internal detail
# ---------------------------------------------------------------------------


@app.exception_handler(AppError)
async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
    log.info("Handled %s: %s", exc.code, exc.message)
    return JSONResponse(status_code=exc.status_code, content=exc.to_payload())


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
    """Turn pydantic's internals into one readable sentence."""
    problems: list[str] = []
    for error in exc.errors():
        location = ".".join(str(part) for part in error.get("loc", ()) if part not in ("body", "query"))
        message = error.get("msg", "is invalid")
        message = message.replace("Value error, ", "")
        problems.append(f"{location or 'request'}: {message}")

    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "validation_error",
                "message": problems[0] if len(problems) == 1 else "Some fields were not valid.",
                "details": problems[:8],
            }
        },
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Last resort.

    The real error goes to the log with a stack trace; the client gets a generic
    message, so no stack trace, file path, SQL or API key can leak to the browser.
    """
    log.exception("Unhandled error on %s %s", request.method, request.url.path)
    del exc
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "internal_error",
                "message": "Something went wrong on the server. Check the backend log for details.",
            }
        },
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

from app.api import (  # noqa: E402  (imported after app creation on purpose)
    routes_cv,
    routes_gap,
    routes_interview,
    routes_jobs,
    routes_metrics,
    routes_system,
)

app.include_router(routes_cv.router, prefix=API_PREFIX)
app.include_router(routes_jobs.router, prefix=API_PREFIX)
app.include_router(routes_gap.router, prefix=API_PREFIX)
app.include_router(routes_interview.router, prefix=API_PREFIX)
app.include_router(routes_metrics.router, prefix=API_PREFIX)
app.include_router(routes_system.router, prefix=API_PREFIX)


@app.get("/", tags=["System"])
def root() -> dict[str, Any]:
    return {
        "app": settings.app_name,
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
        "health": f"{API_PREFIX}/system/health",
        "modules": [
            "1. CV parser (PDF/DOCX -> structured profile)",
            "2. Job posting collection (live) + LLM role skill generation",
            "3. Match and gap analysis",
            "4. CV bullet improvement (with invention guards)",
            "5. Structured voice interview (local STT + local TTS)",
            "6. Rubric-based scoring and feedback",
            "7. Performance measurement and reporting",
        ],
    }


@app.get(f"{API_PREFIX}/ping", tags=["System"])
def ping() -> dict[str, Any]:
    return {"pong": True, "timestamp": time.time()}
