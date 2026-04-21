"""
Shared fixtures for API layer tests.

IMPORTANT: Environment variables must be set BEFORE importing any module
from apps.api because config.py has a module-level ``settings = Settings()``
that crashes if required API keys are missing.

Provides:
    db_path      — temp SQLite file with all migrations applied
    db           — open aiosqlite connection (for direct SQL assertions)
    async_client — httpx AsyncClient wired to the FastAPI app
"""

import os

# Set test env vars BEFORE any app imports
os.environ.setdefault("GEMINI_API_KEY", "test-key")
os.environ.setdefault("MOCK_LLM", "true")
os.environ.setdefault("GOOGLE_CIVIC_API_KEY", "test-key")
os.environ.setdefault("NEWSAPI_KEY", "test-key")
os.environ.setdefault("OPENFEC_API_KEY", "test-key")
os.environ.setdefault("MOCK_EXTERNAL_APIS", "true")
os.environ.setdefault("CORS_ORIGINS", '["http://localhost:3000"]')

import json
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from apps.api.config import settings
from apps.api.db.connection import get_db, run_migrations
from apps.api.main import app
from apps.api.orchestrator.events import (
    BallotFoundEvent,
    IntakeCompleteEvent,
    ItemAnalyzedEvent,
    RankingCompleteEvent,
    ReportCompleteEvent,
)
from apps.api.orchestrator.schemas import (
    BallotReport,
    BallotReportItem,
    ElectionSummary,
    MeasureAnalysis,
    PrecinctInfo,
    SourceCitation,
)


# ─────────────────────────────────────────────
# Database fixtures
# ─────────────────────────────────────────────


@pytest_asyncio.fixture
async def db_path(tmp_path):
    """Temp file path with all migrations applied. Overrides settings.DB_PATH."""
    path = str(tmp_path / "test_api.db")
    await run_migrations(path)
    original = settings.DB_PATH
    settings.DB_PATH = path
    yield path
    settings.DB_PATH = original


@pytest_asyncio.fixture
async def db(db_path):
    """Open aiosqlite connection to a migrated temp DB."""
    async with get_db(db_path) as conn:
        yield conn


# ─────────────────────────────────────────────
# HTTP client fixture
# ─────────────────────────────────────────────


@pytest_asyncio.fixture
async def async_client(db_path):
    """httpx AsyncClient wired to the FastAPI app for testing."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


# ─────────────────────────────────────────────
# Mock orchestrator helpers
# ─────────────────────────────────────────────

_FAKE_SOURCE = SourceCitation(
    name="Test Source",
    url="https://example.com",
    bias_rating=None,
    fetched_at="2026-03-01T00:00:00Z",
)

_FAKE_ELECTION = ElectionSummary(
    id="FL-2026-GEN",
    name="2026 Florida General Election",
    date="2026-11-03",
    state="FL",
)

_FAKE_PRECINCT = PrecinctInfo(
    county="Miami-Dade",
    district=None,
    precinct_id=None,
)

_FAKE_MEASURE = MeasureAnalysis(
    measure_id="FL-2026-A1",
    short_title="Amendment 1",
    plain_english_summary="Test summary.",
    what_yes_means="Yes means X.",
    what_no_means="No means Y.",
    fiscal_impact=None,
    fiscal_impact_source=None,
    proponent_argument="Pro argument.",
    opponent_argument="Con argument.",
    proponent_source="https://example.com/pro",
    opponent_source="https://example.com/con",
    topic_tags=["housing"],
    data_completeness="full",
    sources=[_FAKE_SOURCE],
)


def _fake_report(session_id: str) -> BallotReport:
    return BallotReport(
        session_id=session_id,
        generated_at=datetime.now(timezone.utc).isoformat(),
        election=_FAKE_ELECTION,
        precinct=_FAKE_PRECINCT,
        user_priorities=["housing"],
        items=[
            BallotReportItem(
                item_type="measure",
                relevance_score=8,
                relevance_reason="Affects housing policy.",
                matched_priorities=["housing"],
                measure=_FAKE_MEASURE,
                race=None,
            ),
        ],
    )


@pytest.fixture
def mock_orchestrator(monkeypatch):
    """
    Patches run_orchestrator in the messages router with a generator
    that yields IntakeComplete → BallotFound → ReportComplete.
    """

    async def _mock_run(session_id, message, db_path):
        now = datetime.now(timezone.utc).isoformat()
        yield IntakeCompleteEvent(
            event_type="intake_complete",
            session_id=session_id,
            timestamp=now,
            zip_code="33101",
            priorities=["housing"],
            display_name=None,
        )
        yield BallotFoundEvent(
            event_type="ballot_found",
            session_id=session_id,
            timestamp=now,
            election_name="2026 Florida General Election",
            item_count=1,
            message="Found your ballot — 1 item. Analyzing...",
        )
        yield ReportCompleteEvent(
            event_type="report_complete",
            session_id=session_id,
            timestamp=now,
            report=_fake_report(session_id),
        )

    monkeypatch.setattr(
        "apps.api.routers.messages.run_orchestrator", _mock_run
    )


@pytest.fixture
def mock_orchestrator_error(monkeypatch):
    """
    Patches run_orchestrator to raise RuntimeError after yielding nothing.
    Tests that error handling and DoneEvent still fire.
    """

    async def _mock_run(session_id, message, db_path):
        raise RuntimeError("Simulated orchestrator failure")
        yield  # make it a generator  # noqa: E501

    monkeypatch.setattr(
        "apps.api.routers.messages.run_orchestrator", _mock_run
    )


@pytest.fixture
def mock_orchestrator_with_items(monkeypatch):
    """
    Enhanced mock that yields the full event sequence including
    ItemAnalyzedEvent and RankingCompleteEvent for e2e tests.
    """

    async def _mock_run(session_id, message, db_path):
        now = datetime.now(timezone.utc).isoformat()
        yield IntakeCompleteEvent(
            event_type="intake_complete",
            session_id=session_id,
            timestamp=now,
            zip_code="33101",
            priorities=["housing"],
            display_name=None,
        )
        yield BallotFoundEvent(
            event_type="ballot_found",
            session_id=session_id,
            timestamp=now,
            election_name="2026 Florida General Election",
            item_count=1,
            message="Found your ballot — 1 item. Analyzing...",
        )
        yield ItemAnalyzedEvent(
            event_type="item_analyzed",
            session_id=session_id,
            timestamp=now,
            item_id="FL-2026-A1",
            item_title="Amendment 1",
            items_complete=1,
            items_total=1,
        )
        yield RankingCompleteEvent(
            event_type="ranking_complete",
            session_id=session_id,
            timestamp=now,
            top_item_title="Amendment 1",
        )
        yield ReportCompleteEvent(
            event_type="report_complete",
            session_id=session_id,
            timestamp=now,
            report=_fake_report(session_id),
        )

    monkeypatch.setattr(
        "apps.api.routers.messages.run_orchestrator", _mock_run
    )
