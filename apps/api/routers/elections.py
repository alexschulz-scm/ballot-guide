"""
Elections router — GET /elections.

Returns the list of available elections for the frontend dropdown.
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from apps.api.config import settings
from apps.api.db.connection import get_db
from apps.api.models import APIError, ElectionListItem

router = APIRouter(tags=["elections"])


@router.get("/elections", response_model=list[ElectionListItem])
async def list_elections() -> list[ElectionListItem] | JSONResponse:
    """Returns all FL elections, ordered by date descending."""
    try:
        async with get_db(settings.DB_PATH) as db:
            cursor = await db.execute(
                "SELECT id, name, election_date, is_historical "
                "FROM elections WHERE state = 'FL' "
                "ORDER BY election_date DESC"
            )
            rows = await cursor.fetchall()
    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content=APIError(
                error_code="DB_ERROR",
                message="Failed to list elections.",
                detail=str(exc),
            ).model_dump(),
        )

    return [
        ElectionListItem(
            id=row[0],
            name=row[1],
            election_date=row[2],
            is_historical=bool(row[3]),
        )
        for row in rows
    ]
