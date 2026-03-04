"""
OpenFEC API client for federal campaign finance data.

Fetches candidate finance summaries from the FEC API (api.open.fec.gov)
for federal races (US Senate, US House, President).
Checks MOCK_EXTERNAL_APIS before any real HTTP calls.
"""

import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from mcp_servers.shared.mock_config import is_mock_mode

_OPENFEC_API_BASE = "https://api.open.fec.gov/v1"

# ---------------------------------------------------------------------------
# Mock data
# ---------------------------------------------------------------------------

MOCK_OPENFEC_RESPONSE: dict = {
    "entity_id": "mock_entity",
    "entity_type": "candidate",
    "total_raised": 218000000.0,
    "total_spent": 185000000.0,
    "top_donors": [
        {"name": "Florida GOP", "amount": 5000000.0, "category": "PAC"},
        {"name": "Ken Griffin", "amount": 5000000.0, "category": "individual"},
        {"name": "Steve Schwarzman", "amount": 2500000.0, "category": "individual"},
    ],
    "industry_breakdown": [],
    "reporting_period": "2024",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def fetch_openfec_finance(
    entity_id: str, entity_type: str, api_key: str
) -> dict:
    """
    Return finance data for a federal candidate from OpenFEC.

    Raises ValueError("FINANCE_UNAVAILABLE") on any API or parse failure.
    Raises ValueError("RATE_LIMITED") on 429 responses.
    """
    if is_mock_mode("MOCK_OPENFEC_API"):
        return {
            **MOCK_OPENFEC_RESPONSE,
            "entity_id": entity_id,
            "entity_type": entity_type,
        }

    fec_id = _find_fec_candidate_id(entity_id, api_key)
    totals = _fetch_totals(fec_id, api_key)
    donors = _fetch_top_donors(fec_id, api_key)

    fetched_at = datetime.now(timezone.utc).isoformat()
    return {
        "entity_id": entity_id,
        "entity_type": entity_type,
        "total_raised": totals.get("receipts"),
        "total_spent": totals.get("disbursements"),
        "top_donors": donors,
        "industry_breakdown": [],
        "reporting_period": str(totals.get("cycle", "")),
        "sources": [
            {
                "name": "Federal Election Commission",
                "url": f"https://www.fec.gov/data/candidate/{fec_id}/",
                "fetched_at": fetched_at,
                "bias_rating": None,
            }
        ],
    }


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _find_fec_candidate_id(entity_id: str, api_key: str) -> str:
    """Look up the FEC candidate ID from entity_id or candidate name."""
    params = urllib.parse.urlencode({
        "api_key": api_key,
        "q": entity_id,
        "state": "FL",
        "per_page": 1,
    })
    url = f"{_OPENFEC_API_BASE}/candidates/?{params}"
    data = _make_request(url)

    results = data.get("results", [])
    if not results:
        raise ValueError("ENTITY_NOT_FOUND")
    return results[0]["candidate_id"]


def _fetch_totals(fec_id: str, api_key: str) -> dict:
    """Fetch total raised/spent for a FEC candidate."""
    params = urllib.parse.urlencode({"api_key": api_key, "per_page": 1})
    url = f"{_OPENFEC_API_BASE}/candidates/{fec_id}/totals/?{params}"
    data = _make_request(url)

    results = data.get("results", [])
    if not results:
        return {}
    return results[0]


def _fetch_top_donors(fec_id: str, api_key: str) -> list[dict]:
    """Fetch top 5 individual contributions for a FEC candidate."""
    params = urllib.parse.urlencode({
        "api_key": api_key,
        "candidate_id": fec_id,
        "sort": "-contribution_receipt_amount",
        "per_page": 5,
    })
    url = f"{_OPENFEC_API_BASE}/schedules/schedule_a/?{params}"
    data = _make_request(url)

    return [
        {
            "name": item.get("contributor_name", ""),
            "amount": float(item.get("contribution_receipt_amount", 0)),
            "category": _map_entity_type(item.get("entity_type", "")),
        }
        for item in data.get("results", [])[:5]
    ]


def _map_entity_type(fec_type: str) -> str | None:
    """Map FEC entity type codes to our category values."""
    return {
        "IND": "individual",
        "PAC": "PAC",
        "CCM": "PAC",
        "ORG": "corporation",
        "PTY": "PAC",
        "COM": "PAC",
    }.get(fec_type)


def _make_request(url: str) -> dict:
    """Make a GET request and return the parsed JSON body."""
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            raise ValueError("RATE_LIMITED") from exc
        raise ValueError(f"FINANCE_UNAVAILABLE: HTTP {exc.code}") from exc
    except Exception as exc:
        raise ValueError(f"FINANCE_UNAVAILABLE: {exc}") from exc

    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise ValueError("FINANCE_UNAVAILABLE: invalid JSON") from exc
