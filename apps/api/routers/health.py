"""
Health check router — GET /health.

Used by Azure Container Apps health probe. No /api/v1 prefix.
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Response

from apps.api.config import settings
from apps.api.db.connection import get_db
from apps.api.models import HealthResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check() -> Response:
    """
    Liveness check. Performs a lightweight SQLite read to confirm DB access.
    Returns 503 if DB is unreachable.
    """
    try:
        async with get_db(settings.DB_PATH) as db:
            await db.execute("SELECT 1")
        db_status = "ok"
    except Exception as exc:
        logger.error("Health check DB probe failed: %s", exc)
        db_status = "error"

    status = "ok" if db_status == "ok" else "degraded"
    status_code = 200 if status == "ok" else 503

    body = HealthResponse(
        status=status,
        db=db_status,
        version=settings.APP_VERSION,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
    return Response(
        content=body.model_dump_json(),
        status_code=status_code,
        media_type="application/json",
    )
