"""
Florida Division of Elections fallback client.

Used when the Google Civic API is unavailable. Provides basic precinct
information from a local ZIP→county lookup table. Checks MOCK_EXTERNAL_APIS
before any real network calls.
"""

from mcp_servers.shared.mock_config import is_mock_mode

# ---------------------------------------------------------------------------
# Static lookup: major Florida ZIP codes → county
# ---------------------------------------------------------------------------

FL_ZIP_TO_COUNTY: dict[str, str] = {
    # Miami-Dade
    "33101": "Miami-Dade",
    "33125": "Miami-Dade",
    "33130": "Miami-Dade",
    "33132": "Miami-Dade",
    # Broward
    "33301": "Broward",
    "33316": "Broward",
    "33394": "Broward",
    # Palm Beach
    "33401": "Palm Beach",
    "33415": "Palm Beach",
    # Hillsborough (Tampa)
    "33601": "Hillsborough",
    "33602": "Hillsborough",
    "33606": "Hillsborough",
    # Orange (Orlando)
    "32801": "Orange",
    "32803": "Orange",
    "32827": "Orange",
    # Duval (Jacksonville)
    "32202": "Duval",
    "32207": "Duval",
    # Leon (Tallahassee)
    "32301": "Leon",
    "32303": "Leon",
}

# ---------------------------------------------------------------------------
# Mock data
# ---------------------------------------------------------------------------

MOCK_FL_ELECTIONS_RESPONSE: dict = {
    "county": "Miami-Dade",
    "precinct_id": "PCT-001",
    "district": None,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def fetch_precinct_for_zip(zip_code: str) -> dict:
    """
    Return a precinct-like dict for the given Florida ZIP code.

    Raises ValueError("FL_ELECTIONS_UNAVAILABLE") if the ZIP is not found.
    """
    if is_mock_mode("MOCK_FL_ELECTIONS_API"):
        return MOCK_FL_ELECTIONS_RESPONSE

    county = _lookup_county_for_zip(zip_code)
    if county is None:
        raise ValueError("FL_ELECTIONS_UNAVAILABLE: ZIP not in FL lookup table")

    return _build_precinct_from_zip(zip_code, county)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _lookup_county_for_zip(zip_code: str) -> str | None:
    """Return the county for a ZIP code, or None if not found."""
    return FL_ZIP_TO_COUNTY.get(zip_code.strip())


def _build_precinct_from_zip(zip_code: str, county: str) -> dict:
    """Build a minimal precinct dict from a ZIP code and county name."""
    return {
        "county": county,
        "precinct_id": f"PCT-{zip_code}",
        "district": None,
    }
