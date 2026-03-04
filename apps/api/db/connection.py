import contextlib
import glob
import os

import aiosqlite

from apps.api.db.exceptions import MigrationError

_MIGRATIONS_DIR = os.path.join(os.path.dirname(__file__), "migrations")


def _split_sql_statements(sql: str) -> list[str]:
    """Split a SQL file into individual statements, dropping blank ones."""
    return [s.strip() for s in sql.split(";") if s.strip()]


def _connect_kwargs(db_path: str) -> dict:
    """Build kwargs for aiosqlite.connect — handles URI paths."""
    if db_path.startswith("file:"):
        return {"uri": True}
    return {}


@contextlib.asynccontextmanager
async def get_db(db_path: str):
    """
    Async context manager for SQLite connections.
    Sets WAL mode, enables foreign keys, and configures performance PRAGMAs.
    """
    async with aiosqlite.connect(db_path, **_connect_kwargs(db_path)) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA foreign_keys=ON")
        await db.execute("PRAGMA synchronous=NORMAL")
        await db.execute("PRAGMA cache_size=-64000")
        await db.execute("PRAGMA temp_store=MEMORY")
        db.row_factory = aiosqlite.Row
        yield db


async def _apply_migration(db, filepath: str) -> str | None:
    """Apply a single migration file. Returns filename if applied, None if skipped."""
    filename = os.path.basename(filepath)
    cursor = await db.execute(
        "SELECT 1 FROM _migrations WHERE filename = ?", (filename,)
    )
    if await cursor.fetchone() is not None:
        return None

    with open(filepath, "r", encoding="utf-8") as f:
        sql = f.read()

    try:
        await db.execute("BEGIN")
        for stmt in _split_sql_statements(sql):
            await db.execute(stmt)
        await db.execute(
            "INSERT INTO _migrations (filename) VALUES (?)", (filename,)
        )
        await db.commit()
        print(f"Applied migration: {filename}")
        return filename
    except Exception as exc:
        await db.rollback()
        raise MigrationError(filename, exc) from exc


async def run_migrations(db_path: str) -> list[str]:
    """
    Runs all pending migrations in filename order. Idempotent.
    Returns list of migration filenames applied during this call.
    """
    async with aiosqlite.connect(db_path, **_connect_kwargs(db_path)) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA foreign_keys=ON")
        db.row_factory = aiosqlite.Row

        await db.execute(
            "CREATE TABLE IF NOT EXISTS _migrations ("
            "filename TEXT PRIMARY KEY, "
            "applied_at TEXT NOT NULL DEFAULT (datetime('now')))"
        )
        await db.commit()

        sql_files = sorted(glob.glob(os.path.join(_MIGRATIONS_DIR, "*.sql")))
        applied: list[str] = []
        for filepath in sql_files:
            result = await _apply_migration(db, filepath)
            if result:
                applied.append(result)
        return applied
