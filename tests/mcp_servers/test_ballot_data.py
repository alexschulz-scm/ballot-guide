"""
Tests for the ballot-data-mcp server tools.

All tests run offline: external API calls are mocked via MOCK_EXTERNAL_APIS=true
or via SQLite data only. Uses fixtures from conftest.py.
"""

import pytest

from mcp_servers.ballot_data.constants import TOPIC_TAXONOMY
from mcp_servers.ballot_data.tools.ballot import handle_get_ballot_by_address
from mcp_servers.ballot_data.tools.candidate import handle_get_candidate_detail
from mcp_servers.ballot_data.tools.finance import handle_get_campaign_finance
from mcp_servers.ballot_data.tools.measure import handle_get_measure_detail
from mcp_servers.shared.cache import get_cached, make_cache_key
from mcp_servers.shared.models import (
    BallotResponse,
    CampaignFinanceSummary,
    CandidateDetail,
    CandidatePosition,
    MeasureDetail,
    ToolError,
    GetBallotByAddressInput,
    GetCandidateDetailInput,
    GetCampaignFinanceInput,
    GetMeasureDetailInput,
)


# ---------------------------------------------------------------------------
# Test 1: Ballot cache round-trip
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ballot_cache_roundtrip(db_path, mock_env, fl_address):
    """Second call with same FL address returns cache_hit=True."""
    inp = GetBallotByAddressInput(address=fl_address, election_id="FL-2026-GEN")

    first = handle_get_ballot_by_address(inp, db_path)
    assert isinstance(first, BallotResponse), f"Expected BallotResponse, got: {first}"
    assert first.cache_hit is False

    second = handle_get_ballot_by_address(inp, db_path)
    assert isinstance(second, BallotResponse)
    assert second.cache_hit is True


# ---------------------------------------------------------------------------
# Test 2: Non-FL address returns OUT_OF_STATE
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_non_fl_address_returns_out_of_state(db_path, mock_env, ny_address):
    """A New York address is rejected before any cache write."""
    inp = GetBallotByAddressInput(address=ny_address, election_id=None)
    result = handle_get_ballot_by_address(inp, db_path)

    assert isinstance(result, ToolError)
    assert result.error_code == "OUT_OF_STATE"
    assert result.recoverable is False


# ---------------------------------------------------------------------------
# Test 3: NY zip code returns OUT_OF_STATE before cache write
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ny_zip_returns_out_of_state(db_path, mock_env):
    """A bare NY zip code is rejected with OUT_OF_STATE."""
    inp = GetBallotByAddressInput(address="123 Broadway New York NY 10001", election_id=None)
    result = handle_get_ballot_by_address(inp, db_path)

    assert isinstance(result, ToolError)
    assert result.error_code == "OUT_OF_STATE"
    cache_key = make_cache_key("ballot", "10001", "FL-2026-GEN")
    assert get_cached(cache_key, db_path) is None


# ---------------------------------------------------------------------------
# Test 4: Measure detail reads seeded FL-2022-M2 from SQLite
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_measure_detail_from_sqlite(db_path):
    """FL-2022-M2 (Minimum Wage) is fetched from SQLite without any API call."""
    inp = GetMeasureDetailInput(measure_id="FL-2022-M2", include_full_text=False)
    result = handle_get_measure_detail(inp, db_path)

    assert isinstance(result, MeasureDetail), f"Expected MeasureDetail, got: {result}"
    assert result.id == "FL-2022-M2"
    assert result.passed is True
    assert abs((result.yes_pct or 0) - 60.8) < 0.1
    assert len(result.sources) >= 1
    assert all(s.url != "" for s in result.sources)


# ---------------------------------------------------------------------------
# Test 5: Historical measure has result fields populated
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_historical_measure_has_results(db_path):
    """FL-2022-M4 (Voter Registration) has passed, yes_pct, and no_pct all set."""
    inp = GetMeasureDetailInput(measure_id="FL-2022-M4", include_full_text=False)
    result = handle_get_measure_detail(inp, db_path)

    assert isinstance(result, MeasureDetail)
    assert result.passed is not None
    assert result.yes_pct is not None
    assert result.no_pct is not None


# ---------------------------------------------------------------------------
# Test 6: Unknown measure_id returns MEASURE_NOT_FOUND
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unknown_measure_returns_not_found(db_path, mock_env):
    """A non-existent measure_id returns ToolError(MEASURE_NOT_FOUND)."""
    inp = GetMeasureDetailInput(measure_id="FL-9999-FAKE", include_full_text=False)
    result = handle_get_measure_detail(inp, db_path)

    assert isinstance(result, ToolError)
    assert result.error_code == "MEASURE_NOT_FOUND"
    assert result.recoverable is False


# ---------------------------------------------------------------------------
# Test 7: Candidate detail reads seeded candidate from SQLite
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_candidate_detail_from_sqlite(db_path):
    """DeSantis candidate returns CandidateDetail with typed CandidatePosition objects."""
    inp = GetCandidateDetailInput(candidate_id="cand_desantis_2022", topics=None)
    result = handle_get_candidate_detail(inp, db_path)

    assert isinstance(result, CandidateDetail), f"Expected CandidateDetail, got: {result}"
    assert result.id == "cand_desantis_2022"
    assert "education" in result.positions
    assert isinstance(result.positions["education"], CandidatePosition)
    assert result.positions["education"].topic == "education"
    assert len(result.sources) >= 1


# ---------------------------------------------------------------------------
# Test 8: Topic filter limits returned positions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_candidate_topic_filter(db_path):
    """topics=["education","economy"] returns only those topic keys."""
    inp = GetCandidateDetailInput(
        candidate_id="cand_desantis_2022",
        topics=["education", "economy"],
    )
    result = handle_get_candidate_detail(inp, db_path)

    assert isinstance(result, CandidateDetail)
    assert set(result.positions.keys()).issubset({"education", "economy"})
    assert "environment" not in result.positions


# ---------------------------------------------------------------------------
# Test 9: Unknown candidate_id returns CANDIDATE_NOT_FOUND
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unknown_candidate_returns_not_found(db_path, mock_env):
    """A non-existent candidate_id returns ToolError(CANDIDATE_NOT_FOUND)."""
    inp = GetCandidateDetailInput(candidate_id="cand_fake_9999", topics=None)
    result = handle_get_candidate_detail(inp, db_path)

    assert isinstance(result, ToolError)
    assert result.error_code == "CANDIDATE_NOT_FOUND"
    assert result.recoverable is False


# ---------------------------------------------------------------------------
# Test 10: Campaign finance in mock mode returns valid summary
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_campaign_finance_mock_mode(db_path, mock_env):
    """Finance for seeded candidate returns CampaignFinanceSummary from SQLite."""
    inp = GetCampaignFinanceInput(entity_id="cand_desantis_2022", entity_type="candidate")
    result = handle_get_campaign_finance(inp, db_path)

    assert isinstance(result, CampaignFinanceSummary), f"Expected CampaignFinanceSummary, got: {result}"
    assert result.entity_id == "cand_desantis_2022"
    assert len(result.top_donors) <= 5
    assert len(result.sources) >= 1


# ---------------------------------------------------------------------------
# Test 11: Missing OPENFEC_API_KEY returns FINANCE_UNAVAILABLE for federal
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_campaign_finance_missing_api_key(db_path, monkeypatch):
    """Without an API key and not in mock mode, returns FINANCE_UNAVAILABLE."""
    monkeypatch.setenv("MOCK_EXTERNAL_APIS", "false")
    monkeypatch.delenv("OPENFEC_API_KEY", raising=False)

    # Use a federal entity that has no SQLite funding_summary_json
    inp = GetCampaignFinanceInput(entity_id="fed-fake_no_finance", entity_type="candidate")
    result = handle_get_campaign_finance(inp, db_path)

    assert isinstance(result, ToolError)
    assert result.error_code == "FINANCE_UNAVAILABLE"
    assert result.recoverable is False


# ---------------------------------------------------------------------------
# Test 12: Measure topic_tags contain only valid taxonomy values
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_measure_topic_tags_valid_taxonomy(db_path):
    """FL-2022-M2 topic_tags are all in the canonical topic taxonomy."""
    inp = GetMeasureDetailInput(measure_id="FL-2022-M2", include_full_text=False)
    result = handle_get_measure_detail(inp, db_path)

    assert isinstance(result, MeasureDetail)
    assert len(result.topic_tags) >= 1
    for tag in result.topic_tags:
        assert tag in TOPIC_TAXONOMY, f"'{tag}' is not a valid taxonomy value"


# ---------------------------------------------------------------------------
# Test 13: BallotResponse.sources all have non-empty URLs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ballot_response_sources_have_urls(db_path, mock_env, fl_address):
    """Every source in BallotResponse has a non-empty URL."""
    inp = GetBallotByAddressInput(address=fl_address, election_id="FL-2026-GEN")
    result = handle_get_ballot_by_address(inp, db_path)

    assert isinstance(result, BallotResponse)
    assert len(result.sources) >= 1
    for source in result.sources:
        assert source.url != "", f"Source '{source.name}' has empty URL"


# ---------------------------------------------------------------------------
# AC-MCP-18: Federal entity routes to OpenFEC, not OpenSecrets
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ac_mcp_18_federal_routes_to_openfec(db_path, mock_env, monkeypatch):
    """get_campaign_finance with fed-* entity_id calls OpenFEC, not OpenSecrets."""
    called_with: list[str] = []

    def mock_openfec(entity_id, entity_type, api_key):
        called_with.append("openfec")
        from mcp_servers.ballot_data.sources.openfec import MOCK_OPENFEC_RESPONSE
        return {**MOCK_OPENFEC_RESPONSE, "entity_id": entity_id, "entity_type": entity_type}

    monkeypatch.setattr(
        "mcp_servers.ballot_data.tools.finance.fetch_openfec_finance",
        mock_openfec,
    )

    inp = GetCampaignFinanceInput(entity_id="fed-test-senate", entity_type="candidate")
    result = handle_get_campaign_finance(inp, db_path)

    assert isinstance(result, CampaignFinanceSummary)
    assert "openfec" in called_with


# ---------------------------------------------------------------------------
# AC-MCP-19: State/local entity routes to FL DoE, not OpenFEC
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ac_mcp_19_state_routes_to_fl_doe(db_path, mock_env, monkeypatch):
    """get_campaign_finance with fl-* entity_id calls FL DoE, not OpenFEC."""
    called_with: list[str] = []

    def mock_fl_finance(entity_id, entity_type):
        called_with.append("fl_finance")
        from mcp_servers.ballot_data.sources.fl_finance import MOCK_FL_FINANCE_RESPONSE
        return {**MOCK_FL_FINANCE_RESPONSE, "entity_id": entity_id, "entity_type": entity_type}

    monkeypatch.setattr(
        "mcp_servers.ballot_data.tools.finance.fetch_fl_finance",
        mock_fl_finance,
    )

    inp = GetCampaignFinanceInput(entity_id="fl-test-governor", entity_type="candidate")
    result = handle_get_campaign_finance(inp, db_path)

    assert isinstance(result, CampaignFinanceSummary)
    assert "fl_finance" in called_with


# ---------------------------------------------------------------------------
# AC-MCP-20: Mock mode returns valid CampaignFinanceSummary, no HTTP calls
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ac_mcp_20_mock_mode_no_http(db_path, mock_env):
    """With MOCK_EXTERNAL_APIS=true, returns valid CampaignFinanceSummary with full completeness."""
    inp = GetCampaignFinanceInput(entity_id="fed-mock-test", entity_type="candidate")
    result = handle_get_campaign_finance(inp, db_path)

    assert isinstance(result, CampaignFinanceSummary), f"Expected CampaignFinanceSummary, got: {result}"
    assert result.data_completeness.value == "full"
    assert result.total_raised is not None
    assert len(result.sources) >= 1
