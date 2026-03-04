"""
Reports router — GET /session/{session_id}/report.

Serves cached ballot reports. Never calls the orchestrator.
"""

import json
import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from apps.api.config import settings
from apps.api.models import APIError, ReportResponse
from apps.api.session.store import (
    check_data_freshness,
    get_report,
    get_session,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["reports"])


def _not_found(error_code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content=APIError(error_code=error_code, message=message).model_dump(),
    )


def _processing_response() -> JSONResponse:
    return JSONResponse(
        status_code=202,
        content={
            "status": "processing",
            "message": "Your ballot guide is being prepared. "
            "Connect to the event stream to follow progress.",
        },
    )


@router.get("/session/{session_id}/report", response_model=None)
async def get_session_report(session_id: str) -> ReportResponse | JSONResponse:
    """Returns the most recently completed ballot report for a session."""
    session = await get_session(session_id, settings.DB_PATH)
    if session is None:
        return _not_found("SESSION_NOT_FOUND", f"Session {session_id} not found.")

    if session["status"] == "processing":
        return _processing_response()

    report = await get_report(session_id, settings.DB_PATH)
    if report is None:
        return _not_found("REPORT_NOT_READY", "No report has been generated yet for this session.")

    freshness = await check_data_freshness(session_id, settings.DB_PATH)
    priorities = json.loads(session["priorities_json"]) if session["priorities_json"] else []

    return ReportResponse(
        session_id=session_id,
        report=report,
        generated_at=session["report_generated_at"],
        data_freshness=freshness,
        display_name=session["display_name"],
        priorities=priorities,
    )
