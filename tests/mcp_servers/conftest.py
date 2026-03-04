"""
Shared pytest fixtures for mcp_servers tests.

Provides a seeded temp SQLite database with:
  - All migrations applied
  - FL-2022-GEN historical election + seed candidates + measures
  - FL-2026-GEN future election (for _resolve_upcoming_election tests)
"""

import sys
import os

import aiosqlite
import pytest
import pytest_asyncio

# Make repo root importable so 'scripts' is accessible
_REPO_ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from apps.api.db.connection import run_migrations
from scripts.seed_historical import seed_database


@pytest_asyncio.fixture
async def db_path(tmp_path):
    """
    Migrated and seeded temp DB with both historical and future elections.

    Includes: FL-2022-GEN (historical) + all seed candidates and measures,
    and FL-2026-GEN (upcoming, is_historical=0) for ballot lookup tests.
    """
    path = str(tmp_path / "test_ballot.db")
    await run_migrations(path)
    await seed_database(path)
    await _insert_future_election(path)
    yield path


@pytest.fixture
def mock_env(monkeypatch):
    """Set MOCK_EXTERNAL_APIS=true and stub out all required API keys."""
    monkeypatch.setenv("MOCK_EXTERNAL_APIS", "true")
    monkeypatch.setenv("GOOGLE_CIVIC_API_KEY", "test_key_civic")
    monkeypatch.setenv("OPENFEC_API_KEY", "test_key_openfec")


@pytest.fixture
def fl_address():
    """A valid Florida address for ballot tests."""
    return "123 Main St, Miami FL 33101"


@pytest.fixture
def ny_address():
    """A New York address for out-of-state rejection tests."""
    return "123 Main St, New York NY 10001"


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


async def _insert_future_election(path: str) -> None:
    """Insert a future FL general election for upcoming-election resolution."""
    async with aiosqlite.connect(path) as db:
        await db.execute(
            """
            INSERT OR IGNORE INTO elections
                (id, state, election_type, election_date, name, is_historical)
            VALUES ('FL-2026-GEN', 'FL', 'general', '2026-11-03',
                    '2026 Florida General Election', 0)
            """
        )
        await db.commit()
