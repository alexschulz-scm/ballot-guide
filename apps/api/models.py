"""
Request/response Pydantic models for the API layer.

APIError is used for ALL non-200 error responses — no bare HTTPException.
"""

from pydantic import BaseModel, field_validator


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class CreateSessionRequest(BaseModel):
    display_name: str | None = None
    language: str = "en"
    election_id: str | None = None

    @field_validator("display_name")
    @classmethod
    def truncate_display_name(cls, v: str | None) -> str | None:
        return v[:50] if v else None

    @field_validator("language")
    @classmethod
    def validate_language(cls, v: str) -> str:
        if v not in ["en"]:
            raise ValueError("Unsupported language")
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
