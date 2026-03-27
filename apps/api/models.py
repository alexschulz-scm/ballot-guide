"""
Request/response Pydantic models for the API layer.

APIError is used for ALL non-200 error responses — no bare HTTPException.
"""

import re

from pydantic import BaseModel, field_validator

_ELECTION_ID_RE = re.compile(r"^FL-\d{4}-[A-Z]+$")


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class CreateSessionRequest(BaseModel):
    display_name: str | None = None
    language: str = "en"
    election_id: str | None = None

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, v: str | None) -> str | None:
        if v and len(v) > 50:
            raise ValueError("display_name must be 50 characters or fewer")
        return v

    @field_validator("language")
    @classmethod
    def validate_language(cls, v: str) -> str:
        if v not in ["en"]:
            raise ValueError("Unsupported language")
        return v

    @field_validator("election_id")
    @classmethod
    def validate_election_id(cls, v: str | None) -> str | None:
        if v is not None and not _ELECTION_ID_RE.match(v):
            raise ValueError("Invalid election_id format")
        return v


class SendMessageRequest(BaseModel):
    content: str

    @field_validator("content")
    @classmethod
    def validate_content(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Message cannot be empty")
        if len(v) > 500:
            raise ValueError("Message too long (max 500 characters)")
        return v


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class CreateSessionResponse(BaseModel):
    session_id: str
    created_at: str
    display_name: str | None
    language: str
    status: str
    election_id: str | None = None


class SessionMetadataResponse(BaseModel):
    session_id: str
    created_at: str
    updated_at: str
    display_name: str | None
    language: str
    status: str
    zip_code: str | None
    priorities: list[str]
    has_report: bool
    election_name: str | None
    message_count: int


class ReportResponse(BaseModel):
    session_id: str
    report: dict
    generated_at: str
    data_freshness: str
    display_name: str | None
    priorities: list[str]


class ElectionListItem(BaseModel):
    id: str
    name: str
    election_date: str
    is_historical: bool


class HealthResponse(BaseModel):
    status: str
    db: str
    version: str
    timestamp: str


# ---------------------------------------------------------------------------
# Error model — used for all non-200 responses
# ---------------------------------------------------------------------------


class APIError(BaseModel):
    error_code: str  # SCREAMING_SNAKE_CASE
    message: str  # user-facing message
    detail: str | None = None  # additional technical detail (dev/debug only)
