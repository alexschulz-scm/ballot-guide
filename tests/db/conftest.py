import os
import tempfile

import pytest
import pytest_asyncio

from apps.api.db.connection import get_db, run_migrations


def _make_db_path() -> str:
    """Create a unique temp file path; SQLite will create the DB on first connect."""
    fd, path = tempfile.mkstemp(suffix=".db", prefix="ballot_test_")
    os.close(fd)
    os.unlink(path)
    return path


@pytest_asyncio.fixture
async def db_path(tmp_path):
    """Temp file path with all migrations applied. Yields the path string."""
    path = str(tmp_path / "test.db")
    await run_migrations(path)
    yield path


@pytest_asyncio.fixture
async def db(db_path):
    """Open aiosqlite connection to a migrated temp DB."""
    async with get_db(db_path) as conn:
        yield conn
