"""
FL Division of Elections finance client for state/local campaign data.

Fetches campaign finance data from FL Division of Elections bulk CSV
downloads for state and local races.
Checks MOCK_EXTERNAL_APIS before any real HTTP calls.
"""

import csv
import io
import urllib.error
import urllib.request
from datetime import datetime, timezone

from mcp_servers.shared.mock_config import is_mock_mode

_FL_FINANCE_URL = (
    "https://dos.elections.myflorida.com/campaign-finance/contributions/"
)

# ---------------------------------------------------------------------------
# Mock data
# ---------------------------------------------------------------------------

MOCK_FL_FINANCE_RESPONSE: dict = {
    "entity_id": "mock_entity",
    "entity_type": "candidate",
    "total_raised": 45000000.0,
    "total_spent": 38000000.0,
    "top_donors": [
        {"name": "FL Democratic Party", "amount": 2000000.0, "category": None},
        {"name": "Jane Smith", "amount": 500000.0, "category": None},
        {"name": "Acme Corp PAC", "amount": 250000.0, "category": None},
    ],
    "industry_breakdown": [],
    "reporting_period": "2026",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def fetch_fl_finance(entity_id: str, entity_type: str) -> dict:
    """
    Return finance data for a state/local candidate from FL DoE.

    No API key required — uses public bulk CSV downloads.
    Raises ValueError("FINANCE_UNAVAILABLE") on any failure.
    """
    if is_mock_mode("MOCK_FL_FINANCE_API"):
        return {
            **MOCK_FL_FINANCE_RESPONSE,
            "entity_id": entity_id,
            "entity_type": entity_type,
        }

    csv_text = _download_csv()
    contributions, expenditures = _parse_csv(csv_text, entity_id)

    if not contributions and not expenditures:
        raise ValueError("ENTITY_NOT_FOUND")

    total_raised = sum(row["amount"] for row in contributions)
    total_spent = sum(row["amount"] for row in expenditures)

    top_donors = [
        {
            "name": row["contributor_name"],
            "amount": row["amount"],
            "category": None,
        }
        for row in sorted(
            contributions, key=lambda r: r["amount"], reverse=True
        )[:5]
    ]

    fetched_at = datetime.now(timezone.utc).isoformat()
    return {
        "entity_id": entity_id,
        "entity_type": entity_type,
        "total_raised": total_raised,
        "total_spent": total_spent,
        "top_donors": top_donors,
        "industry_breakdown": [],
        "reporting_period": str(datetime.now().year),
        "sources": [
            {
                "name": "Florida Division of Elections",
                "url": _FL_FINANCE_URL,
                "fetched_at": fetched_at,
                "bias_rating": None,
            }
        ],
    }


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _download_csv() -> str:
    """Download the FL DoE campaign finance CSV."""
    try:
        with urllib.request.urlopen(_FL_FINANCE_URL, timeout=30) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            raise ValueError("RATE_LIMITED") from exc
        raise ValueError(f"FINANCE_UNAVAILABLE: HTTP {exc.code}") from exc
    except Exception as exc:
        raise ValueError(f"FINANCE_UNAVAILABLE: {exc}") from exc


def _parse_csv(
    csv_text: str, entity_id: str
) -> tuple[list[dict], list[dict]]:
    """Parse CSV and return (contributions, expenditures) for entity_id."""
    contributions: list[dict] = []
    expenditures: list[dict] = []

    reader = csv.DictReader(io.StringIO(csv_text))
    for row in reader:
        candidate_id = row.get("candidate_id", "").strip()
        if candidate_id != entity_id:
            continue

        amount = _safe_float(row.get("amount", "0"))
        if amount is None:
            continue

        record = {
            "contributor_name": row.get("contributor_name", "").strip(),
            "amount": amount,
        }

        record_type = row.get("type", "").strip().lower()
        if record_type == "expenditure":
            expenditures.append(record)
        else:
            contributions.append(record)

    return contributions, expenditures


def _safe_float(value: str) -> float | None:
    """Convert a string to float, returning None on failure."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
