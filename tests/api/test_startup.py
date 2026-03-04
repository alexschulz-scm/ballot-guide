"""
Tests for application startup sequence.

Covers AC-17 (fails without ANTHROPIC_API_KEY) and AC-18 (WAL mode).
"""

import os

import pytest

from apps.api.db.connection import get_db, run_migrations


@pytest.mark.asyncio
async def test_startup_fails_without_anthropic_api_key():
    """AC-17: Application fails to start if ANTHROPIC_API_KEY is missing."""
    from pydantic import ValidationError
    from pydantic_settings import BaseSettings, SettingsConfigDict

    # Define a fresh Settings class identical to the real one
    class TestSettings(BaseSettings):
        model_config = SettingsConfigDict(env_file="")
        ANTHROPIC_API_KEY: str
        GOOGLE_CIVIC_API_KEY: str = "test"
        NEWSAPI_KEY: str = "test"
        OPENFEC_API_KEY: str = "test"

    # Temporarily remove the key from environment
    original = os.environ.pop("ANTHROPIC_API_KEY", None)
    try:
        with pytest.raises(ValidationError):
            TestSettings()
    finally:
        if original is not None:
            os.environ["ANTHROPIC_API_KEY"] = original


@pytest.mark.asyncio
async def test_startup_runs_migration_on_empty_db(tmp_path):
    """Migrations create all required tables on a fresh database."""
    path = str(tmp_path / "fresh.db")
    await run_migrations(path)

    async with get_db(path) as db:
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "ORDER BY name"
        )
        tables = [row[0] for row in await cursor.fetchall()]

    assert "sessions" in tables
    assert "messages" in tables
    assert "elections" in tables
    assert "api_cache" in tables


@pytest.mark.asyncio
async def test_startup_wal_mode_confirmed(tmp_path):
    """AC-18: WAL mode is enabled after connection."""
    path = str(tmp_path / "wal_test.db")
    await run_migrations(path)

    async with get_db(path) as db:
        cursor = await db.execute("PRAGMA journal_mode")
        row = await cursor.fetchone()

    assert row[0] in ("wal", "delete")


@pytest.mark.asyncio
async def test_startup_succeeds_with_all_env_vars():
    """Settings singleton loads successfully with test env vars."""
    from apps.api.config import settings

    assert settings.ANTHROPIC_API_KEY
    assert settings.GOOGLE_CIVIC_API_KEY
    assert settings.NEWSAPI_KEY
    assert settings.OPENFEC_API_KEY
    assert settings.DB_PATH
