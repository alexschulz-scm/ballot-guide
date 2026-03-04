"""
Tool handler: get_campaign_finance

Returns a campaign finance summary for a candidate or measure. Reads from
SQLite (funding_summary_json) first, then falls back to OpenFEC (federal)
or FL Division of Elections (state/local).
"""

import json
import os
import sqlite3
from datetime import datetime, timezone

from mcp_servers.shared.mock_config import is_mock_mode

from mcp_servers.ballot_data.constants import FINANCE_CACHE_TTL_SECONDS, MAX_TOP_DONORS
from mcp_servers.ballot_data.sources.fl_finance import fetch_fl_finance
from mcp_servers.ballot_data.sources.openfec import fetch_openfec_finance
from mcp_servers.shared.cache import get_cached, make_cache_key, set_cached
from mcp_servers.shared.models import (
    CampaignFinanceSummary,
    DataCompleteness,
    DonorSummary,
    GetCampaignFinanceInput,
    IndustryDonation,
    SourceCitation,
    ToolError,
)

def handle_get_campaign_finance(
    inp: GetCampaignFinanceInput, db_path: str
) -> CampaignFinanceSummary | ToolError:
    """Return campaign finance summary, cache-first, SQLite-primary."""
    cache_key = make_cache_key("finance", inp.entity_id)

    cached = get_cached(cache_key, db_path)
    if cached is not None:
        return CampaignFinanceSummary.model_validate({**cached, "data_completeness": cached.get("data_completeness", "full")})

    sqlite_data = _fetch_finance_from_sqlite(inp.entity_id, inp.entity_type, db_path)
    if sqlite_data is not None:
        result = _build_finance_from_sqlite(sqlite_data, inp.entity_id, inp.entity_type)
        set_cached(cache_key, result.model_dump(), FINANCE_CACHE_TTL_SECONDS, "sqlite", db_path)
        return result

    return _fetch_from_external_source(inp, cache_key, db_path)


def _fetch_from_external_source(
    inp: GetCampaignFinanceInput, cache_key: str, db_path: str
) -> CampaignFinanceSummary | ToolError:
    """Route to OpenFEC (federal) or FL DoE (state/local) based on entity_id prefix."""
    if _is_federal(inp.entity_id):
        return _fetch_federal(inp, cache_key, db_path)
    if _is_state_local(inp.entity_id):
        return _fetch_state_local(inp, cache_key, db_path)
    # Unknown prefix: try OpenFEC first, fallback to FL DoE
    result = _fetch_federal(inp, cache_key, db_path)
    if not isinstance(result, ToolError):
        return result
    return _fetch_state_local(inp, cache_key, db_path)


def _is_federal(entity_id: str) -> bool:
    return entity_id.startswith("fed-")


def _is_state_local(entity_id: str) -> bool:
    return entity_id.startswith("fl-") or entity_id.startswith("local-")


def _fetch_federal(
    inp: GetCampaignFinanceInput, cache_key: str, db_path: str,
) -> CampaignFinanceSummary | ToolError:
    """Fetch from OpenFEC API for federal races."""
    api_key = os.environ.get("OPENFEC_API_KEY", "")
    if not api_key and not is_mock_mode("MOCK_OPENFEC_API"):
        return ToolError(
            error_code="FINANCE_UNAVAILABLE",
            message="OPENFEC_API_KEY is not set",
            recoverable=False,
            fallback_source=None,
        )
    try:
        raw = fetch_openfec_finance(inp.entity_id, inp.entity_type, api_key)
    except ValueError as exc:
        return ToolError(
            error_code=str(exc) if str(exc) in ("RATE_LIMITED", "ENTITY_NOT_FOUND") else "FINANCE_UNAVAILABLE",
            message=str(exc),
            recoverable=str(exc) != "ENTITY_NOT_FOUND",
            fallback_source=None,
        )
    result = _build_finance_from_api(raw, inp.entity_id, inp.entity_type)
    set_cached(cache_key, result.model_dump(), FINANCE_CACHE_TTL_SECONDS, "openfec", db_path)
    return result


def _fetch_state_local(
    inp: GetCampaignFinanceInput, cache_key: str, db_path: str,
) -> CampaignFinanceSummary | ToolError:
    """Fetch from FL Division of Elections for state/local races."""
    try:
        raw = fetch_fl_finance(inp.entity_id, inp.entity_type)
    except ValueError as exc:
        return ToolError(
            error_code=str(exc) if str(exc) in ("RATE_LIMITED", "ENTITY_NOT_FOUND") else "FINANCE_UNAVAILABLE",
            message=str(exc),
            recoverable=str(exc) != "ENTITY_NOT_FOUND",
            fallback_source=None,
        )
    result = _build_finance_from_api(raw, inp.entity_id, inp.entity_type)
    set_cached(cache_key, result.model_dump(), FINANCE_CACHE_TTL_SECONDS, "fl_finance", db_path)
    return result


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _fetch_finance_from_sqlite(
    entity_id: str, entity_type: str, db_path: str
) -> dict | None:
    """Return raw funding_summary_json dict from the candidates table, or None."""
    if entity_type != "candidate":
        return None
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT funding_summary_json, ballotpedia_url, fl_elections_url, fetched_at "
            "FROM candidates WHERE id = ?",
            (entity_id,),
        ).fetchone()
    if row is None or not row["funding_summary_json"]:
        return None
    try:
        data = json.loads(row["funding_summary_json"])
        data["_ballotpedia_url"] = row["ballotpedia_url"]
        data["_fl_elections_url"] = row["fl_elections_url"]
        data["_fetched_at"] = row["fetched_at"]
        return data
    except json.JSONDecodeError:
        return None


def _build_finance_from_sqlite(
    raw: dict, entity_id: str, entity_type: str
) -> CampaignFinanceSummary:
    """Build CampaignFinanceSummary from a SQLite funding_summary_json dict."""
    top_donors = _parse_top_donors(raw.get("top_donors", []))
    fetched_at = raw.get("_fetched_at") or datetime.now(timezone.utc).isoformat()

    sources = []
    if raw.get("_ballotpedia_url"):
        sources.append(SourceCitation(
            name="Ballotpedia",
            url=raw["_ballotpedia_url"],
            fetched_at=fetched_at,
            bias_rating=None,
        ))
    if raw.get("_fl_elections_url"):
        sources.append(SourceCitation(
            name="Florida Division of Elections",
            url=raw["_fl_elections_url"],
            fetched_at=fetched_at,
            bias_rating=None,
        ))
    if not sources:
        sources.append(SourceCitation(
            name="Florida Division of Elections",
            url="https://dos.myflorida.com/elections/",
            fetched_at=fetched_at,
            bias_rating=None,
        ))

    total = raw.get("total_raised")
    return CampaignFinanceSummary(
        entity_id=entity_id,
        entity_type=entity_type,
        total_raised=float(total) if total is not None else None,
        total_spent=None,
        top_donors=top_donors,
        industry_breakdown=None,
        reporting_period=None,
        sources=sources,
        data_completeness=DataCompleteness.PARTIAL,
    )


def _build_finance_from_api(
    raw: dict, entity_id: str, entity_type: str
) -> CampaignFinanceSummary:
    """Build CampaignFinanceSummary from an OpenSecrets API response dict."""
    top_donors = _parse_top_donors(raw.get("top_donors", []))
    industry_raw = raw.get("industry_breakdown") or []
    industry = [
        IndustryDonation(
            industry=item.get("industry", ""),
            amount=float(item.get("amount", 0)),
            pct_of_total=float(item.get("pct_of_total", 0)),
        )
        for item in industry_raw
        if isinstance(item, dict)
    ]

    fetched_at = datetime.now(timezone.utc).isoformat()
    sources_raw = raw.get("sources", [])
    sources = []
    for s in sources_raw:
        try:
            sources.append(SourceCitation.model_validate(s))
        except Exception:
            continue
    if not sources:
        sources.append(SourceCitation(
            name="Federal Election Commission",
            url=f"https://www.fec.gov/data/candidate/{entity_id}/",
            fetched_at=fetched_at,
            bias_rating=None,
        ))

    return CampaignFinanceSummary(
        entity_id=entity_id,
        entity_type=entity_type,
        total_raised=raw.get("total_raised"),
        total_spent=raw.get("total_spent"),
        top_donors=top_donors,
        industry_breakdown=industry or None,
        reporting_period=raw.get("reporting_period"),
        sources=sources,
        data_completeness=DataCompleteness.FULL,
    )


def _parse_top_donors(raw_donors: list) -> list[DonorSummary]:
    """Convert raw donor dicts to DonorSummary models, capped at MAX_TOP_DONORS."""
    donors = []
    for d in raw_donors[:MAX_TOP_DONORS]:
        try:
            donors.append(DonorSummary(
                name=d["name"],
                amount=float(d["amount"]),
                category=d.get("category"),
            ))
        except (KeyError, TypeError, ValueError):
            continue
    return donors
