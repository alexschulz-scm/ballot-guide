"""
Messages router — POST /session/{session_id}/message (SSE).

The most critical router. Accepts a user message, invokes the orchestrator,
and streams events back as Server-Sent Events.

Non-negotiables:
- X-Accel-Buffering: no header on every SSE response
- done event fires in finally block — always, even on error paths
- done event uses DoneEvent model (has timestamp)
- 409 SESSION_BUSY if session.status == "processing"
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter
from fastapi.responses import JSONResponse, StreamingResponse

from apps.api.config import settings
from apps.api.models import APIError, SendMessageRequest
from apps.api.orchestrator.events import DoneEvent, ErrorEvent
from apps.api.orchestrator.runner import run_orchestrator
from apps.api.session.store import (
    get_session,
    save_message,
    update_session_status,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["messages"])


def _session_not_found(session_id: str) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content=APIError(
            error_code="SESSION_NOT_FOUND",
            message=f"Session {session_id} not found.",
        ).model_dump(),
    )


def _session_busy() -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content=APIError(
            error_code="SESSION_BUSY",
            message="An analysis is already in progress for this session.",
        ).model_dump(),
    )


async def _safe_set_status(
    session_id: str, status: str, db_path: str
) -> None:
    """Set session status, swallowing exceptions to protect finally blocks."""
    try:
        await update_session_status(session_id, status, db_path)
    except Exception:
        logger.error("Failed to set status=%s for session %s", status, session_id)


async def _handle_error(session_id, exc, db_path):
    """Build error SSE payload and set session to error state."""
    logger.error("Orchestrator failed for session %s: %s", session_id, exc)
    error_event = ErrorEvent(
        event_type="error",
        session_id=session_id,
        timestamp=datetime.now(timezone.utc).isoformat(),
        error_code="ORCHESTRATOR_ERROR",
        message="An unexpected error occurred. Please try again.",
        recoverable=True,
    )
    await _safe_set_status(session_id, "error", db_path)
    return f"event: error\ndata: {error_event.model_dump_json()}\n\n"


async def event_generator(session_id, message, db_path):
    """Wrap run_orchestrator as SSE. DoneEvent always in finally."""
    assistant_text = ""
    try:
        async for event in run_orchestrator(session_id, message, db_path):
            yield f"event: {event.event_type}\ndata: {event.model_dump_json()}\n\n"
            if event.event_type == "clarification_needed":
                assistant_text = event.question
            elif event.event_type == "report_complete":
                assistant_text = f"Generated ballot guide for {event.report.election.name}."
        await _safe_set_status(session_id, "active", db_path)
    except Exception as exc:
        yield await _handle_error(session_id, exc, db_path)
        assistant_text = "An error occurred while generating your ballot guide."
    finally:
        if assistant_text:
            try:
                await save_message(session_id, "assistant", assistant_text, db_path)
            except Exception:
                logger.warning("Failed to save assistant message for %s", session_id)
        done = DoneEvent(
            event_type="done", session_id=session_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        yield f"event: done\ndata: {done.model_dump_json()}\n\n"


@router.post("/session/{session_id}/message", response_model=None)
async def send_message(
    session_id: str, body: SendMessageRequest
) -> StreamingResponse | JSONResponse:
    """Accept a user message, run the orchestrator, stream events as SSE."""
    db_path = settings.DB_PATH

    session = await get_session(session_id, db_path)
    if session is None:
        return _session_not_found(session_id)

    if session["status"] == "processing":
        return _session_busy()

    await update_session_status(session_id, "processing", db_path)
    await save_message(session_id, "user", body.content, db_path)

    return StreamingResponse(
        event_generator(session_id, body.content, db_path),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
