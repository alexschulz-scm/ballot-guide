"""
FastAPI application entry point.

Startup sequence (order matters):
1. Validate required environment variables
2. Ensure data directory exists
3. Run database migrations
4. Log startup confirmation
"""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from apps.api.config import settings
from apps.api.db.connection import run_migrations
from apps.api.middleware.logging import RequestLoggingMiddleware
from apps.api.models import APIError
from apps.api.routers.elections import router as elections_router
from apps.api.routers.health import router as health_router
from apps.api.routers.messages import router as messages_router
from apps.api.routers.reports import router as reports_router
from apps.api.routers.sessions import router as sessions_router

logger = logging.getLogger(__name__)


# ── Lifespan ────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup sequence — order matters.
    If any step fails, the application fails to start (intentional).
    """
    # 1. Validate required env vars and log confirmation
    settings.validate_required()

    # 1b. Export API keys to os.environ so MCP server tools can read them.
    # Pydantic-settings loads .env into Settings but not into os.environ.
    os.environ.setdefault("GOOGLE_CIVIC_API_KEY", settings.GOOGLE_CIVIC_API_KEY)
    os.environ.setdefault("NEWSAPI_KEY", settings.NEWSAPI_KEY)
    os.environ.setdefault("OPENFEC_API_KEY", settings.OPENFEC_API_KEY)
    os.environ.setdefault("MOCK_EXTERNAL_APIS", str(settings.MOCK_EXTERNAL_APIS).lower())

    # Per-source mock flags
    os.environ.setdefault("MOCK_CIVIC_API", str(settings.MOCK_CIVIC_API).lower())
    os.environ.setdefault("MOCK_OPENFEC_API", str(settings.MOCK_OPENFEC_API).lower())
    os.environ.setdefault("MOCK_FL_FINANCE_API", str(settings.MOCK_FL_FINANCE_API).lower())
    os.environ.setdefault("MOCK_BALLOTPEDIA_API", str(settings.MOCK_BALLOTPEDIA_API).lower())
    os.environ.setdefault("MOCK_FL_ELECTIONS_API", str(settings.MOCK_FL_ELECTIONS_API).lower())
    os.environ.setdefault("MOCK_NEWSAPI", str(settings.MOCK_NEWSAPI).lower())
    os.environ.setdefault("MOCK_LEGISLATION_API", str(settings.MOCK_LEGISLATION_API).lower())

    # 2. Ensure data directory exists (Azure File Share mount point)
    db_dir = os.path.dirname(settings.DB_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

    # 3. Run database migrations
    await run_migrations(settings.DB_PATH)

    # 4. Log startup complete
    logger.info("Ballot Guide API started. DB: %s", settings.DB_PATH)

    yield
    # Shutdown — nothing needed for MVP


app = FastAPI(
    title="Ballot Guide API",
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

# ── Middleware ───────────────────────────────────────────
# Request logging (raw ASGI — safe with StreamingResponse)
app.add_middleware(RequestLoggingMiddleware)

# CORS — origins from config, never hardcoded.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

# ── Routers ──────────────────────────────────────────────
app.include_router(health_router)  # no prefix — /health
app.include_router(elections_router, prefix="/api/v1")
app.include_router(sessions_router, prefix="/api/v1")
app.include_router(messages_router, prefix="/api/v1")
app.include_router(reports_router, prefix="/api/v1")


# ── Validation error handler ────────────────────────────
# Returns APIError model instead of FastAPI's default 422 format.
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request, exc: RequestValidationError
) -> JSONResponse:
    errors = exc.errors()
    first = errors[0] if errors else {}
    msg = first.get("msg", "Validation error")
    field = ".".join(str(loc) for loc in first.get("loc", []))
    detail = f"{field}: {msg}" if field else msg

    return JSONResponse(
        status_code=422,
        content=APIError(
            error_code="VALIDATION_ERROR",
            message=msg,
            detail=detail,
        ).model_dump(),
    )
