"""
Sessions router — POST /session, GET /session/{session_id}.

Thin routing layer: validate input, delegate to session store, format response.
"""

import json
import logging
import re

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address

from apps.api.config import settings
from apps.api.models import (
    APIError,
    CreateSessionRequest,
    CreateSessionResponse,
    SessionMetadataResponse,
)
from apps.api.session.store import (
    count_messages,
    create_session,
    get_session,
)

logger = logging.getLogger(__name__)

limiter = Limiter(key_func=get_remote_address)

router = APIRouter(tags=["sessions"])

_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


@router.post("/session", status_code=201, response_model=CreateSessionResponse)
@limiter.limit("20/minute")
async def create_new_session(
    request: Request,
    body: CreateSessionRequest = CreateSessionRequest(),
) -> CreateSessionResponse:
    """Creates a new anonymous session."""
    # Extract browser language from Accept-Language header safely
    accept_lang = request.headers.get("accept-language")
    detected_language = None
    if accept_lang:
        lang_match = re.match(r"([a-zA-Z]{2}(?:-[a-zA-Z]{2})?)", accept_lang)
        detected_language = lang_match.group(1).lower() if lang_match else None

    try:
        session_id = await create_session(
            body.display_name,
            body.language,
            detected_language,
            settings.DB_PATH,
            body.election_id,
        )
    except Exception as exc:
        logger.error("Failed to create session: %s", exc, exc_info=True)
        return JSONResponse(
            status_code=500,
            content=APIError(
                error_code="DB_ERROR",
                message="Failed to create session.",
            ).model_dump(),
        )

    session = await get_session(session_id, settings.DB_PATH)
    return CreateSessionResponse(
        session_id=session["id"],
        created_at=session["created_at"],
        display_name=session["display_name"],
        language=session["language"],
        status=session["status"],
        election_id=session.get("ballot_id"),
    )


@router.get("/session/{session_id}", response_model=None)
async def get_session_metadata(session_id: str) -> SessionMetadataResponse | JSONResponse:
    """Returns session metadata. Never returns the full report."""
    if not _UUID_RE.match(session_id):
        return JSONResponse(
            status_code=404,
            content=APIError(
                error_code="SESSION_NOT_FOUND",
                message="Session not found.",
            ).model_dump(),
        )

    session = await get_session(session_id, settings.DB_PATH)
    if session is None:
        return JSONResponse(
            status_code=404,
            content=APIError(
                error_code="SESSION_NOT_FOUND",
                message="Session not found.",
            ).model_dump(),
        )

    msg_count = await count_messages(session_id, settings.DB_PATH)
    priorities = json.loads(session["priorities_json"]) if session["priorities_json"] else []

    return SessionMetadataResponse(
        session_id=session["id"],
        created_at=session["created_at"],
        updated_at=session["updated_at"],
        display_name=session["display_name"],
        language=session["language"],
        status=session["status"],
        zip_code=session["zip_code"],
        priorities=priorities,
        has_report=session["report_json"] is not None,
        election_name=session["election_name"],
        message_count=msg_count,
    )
