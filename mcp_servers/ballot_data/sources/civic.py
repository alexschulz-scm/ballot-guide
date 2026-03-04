"""
Google Civic Information API client.

Fetches voter information (ballot contests, candidates, polling places) for
a given address. Checks MOCK_EXTERNAL_APIS before making any real HTTP calls.
"""

import json
import urllib.error
import urllib.parse
import urllib.request

from mcp_servers.shared.mock_config import is_mock_mode

_CIVIC_VOTERINFO_URL = "https://www.googleapis.com/civicinfo/v2/voterinfo"

# ---------------------------------------------------------------------------
# Mock data — returned when MOCK_EXTERNAL_APIS=true
# ---------------------------------------------------------------------------

MOCK_CIVIC_RESPONSE: dict = {
    "normalizedInput": {
        "line1": "123 Main St",
        "city": "Miami",
        "state": "FL",
        "zip": "33101",
    },
    "election": {
        "id": "FL-2026-GEN",
        "name": "2026 Florida General Election",
        "electionDay": "2026-11-03",
        "ocdDivisionId": "ocd-division/country:us/state:fl",
    },
    "contests": [],
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def fetch_ballot_for_address(address: str, api_key: str) -> dict:
    """
    Return the Civic API voterinfo response for the given address.

    Raises ValueError with a machine-readable code on any failure.
    """
    if is_mock_mode("MOCK_CIVIC_API"):
        return MOCK_CIVIC_RESPONSE

    params = urllib.parse.urlencode({
        "key": api_key,
        "address": address,
        "returnAllAvailableData": "false",
    })
    url = f"{_CIVIC_VOTERINFO_URL}?{params}"
    return _make_civic_request(url)


def extract_zip_from_address(address: str) -> str | None:
    """Extract a 5-digit ZIP code from an address string, or return None."""
    import re
    match = re.search(r"\b(\d{5})\b", address)
    return match.group(1) if match else None


def extract_state_from_civic_response(response: dict) -> str | None:
    """Extract the normalized state code from a Civic API response."""
    state = response.get("normalizedInput", {}).get("state", "")
    return state.upper() or None


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _make_civic_request(url: str) -> dict:
    """Make a GET request to the Civic API and return the parsed JSON body."""
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raise ValueError(f"CIVIC_UNAVAILABLE: HTTP {exc.code}") from exc
    except Exception as exc:
        raise ValueError(f"CIVIC_UNAVAILABLE: {exc}") from exc

    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise ValueError("CIVIC_UNAVAILABLE: invalid JSON response") from exc
