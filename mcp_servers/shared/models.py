"""
Shared Pydantic models used by all MCP servers and the agent orchestrator.

This is the single source of truth for all shared types. No model definitions
should exist in tool files — import from here instead.

Naming note: SourceCitation is the canonical name for source attribution.
DataSource is a retired alias from before the integration review.
"""

from enum import Enum
from urllib.parse import urlparse

from pydantic import BaseModel, field_validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class DataCompleteness(str, Enum):
    """Signal to the UI about how complete the returned data is."""

    FULL = "full"       # all expected fields populated
    PARTIAL = "partial" # some optional fields missing
    LIMITED = "limited" # only basics available (name, type, status)


# ---------------------------------------------------------------------------
# Shared primitive types
# ---------------------------------------------------------------------------


class SourceCitation(BaseModel):
    """Provenance record attached to every piece of returned data."""

    name: str                  # "Ballotpedia", "Google Civic API"
    url: str                   # direct URL to the source record
    fetched_at: str            # ISO 8601 datetime string
    bias_rating: str | None    # AllSides rating if applicable, else null

    @field_validator("url")
    @classmethod
    def validate_url_protocol(cls, v: str) -> str:
        """Reject javascript: and data: URLs to prevent XSS."""
        parsed = urlparse(v)
        if parsed.scheme and parsed.scheme not in ("http", "https", ""):
            raise ValueError(f"Invalid URL scheme: {parsed.scheme}")
        return v


class ToolError(BaseModel):
    """Structured error returned by any tool handler. Never raise raw exceptions."""

    error_code: str            # machine-readable, SCREAMING_SNAKE_CASE
    message: str               # human-readable, for logging
    recoverable: bool          # can the agent retry or use a fallback?
    fallback_source: str | None  # if recoverable, what to try next


# ---------------------------------------------------------------------------
# ballot-data-mcp output models
# ---------------------------------------------------------------------------


class ElectionSummary(BaseModel):
    """Top-level election context returned with ballot data."""

    id: str     # "FL-2026-GEN"
    name: str   # "2026 Florida General Election"
    date: str   # "2026-11-03" — maps to DB column election_date
    state: str  # "FL"


class PrecinctInfo(BaseModel):
    """Voter's resolved precinct."""

    county: str
    district: str | None
    precinct_id: str | None


class RaceSummary(BaseModel):
    """Brief race descriptor included in BallotResponse."""

    id: str
    type: str             # "governor" | "us_senate" | "state_senate" |
                          # "state_house" | "judicial_retention" | "local"
    title: str
    candidate_ids: list[str]


class MeasureSummary(BaseModel):
    """Brief measure descriptor included in BallotResponse."""

    id: str            # "FL-2026-A1"
    type: str          # "constitutional_amendment" | "referendum" | "bond"
    short_title: str   # "Amendment 1"
    full_title: str


class BallotResponse(BaseModel):
    """Full ballot for a voter's address."""

    election: ElectionSummary
    precinct: PrecinctInfo
    races: list[RaceSummary]
    measures: list[MeasureSummary]
    sources: list[SourceCitation]
    cache_hit: bool
    data_completeness: DataCompleteness


class MeasureDetail(BaseModel):
    """Full structured profile of a ballot measure."""

    id: str
    short_title: str
    full_title: str
    type: str
    summary: str | None               # Ballotpedia summary, not LLM-generated
    status: str                       # "on_ballot" | "passed" | "failed" | "withdrawn"
    election_id: str
    topic_tags: list[str]             # mapped to internal taxonomy keys
    proponent_argument: str | None    # from official FL voter guide
    opponent_argument: str | None     # from official FL voter guide
    fiscal_impact: str | None
    fiscal_impact_source: str | None
    passed: bool | None               # null = upcoming
    yes_pct: float | None
    no_pct: float | None
    full_text: str | None             # only if include_full_text=True
    ballotpedia_url: str | None
    fl_elections_url: str | None
    sources: list[SourceCitation]
    data_completeness: DataCompleteness


class CandidatePosition(BaseModel):
    """A candidate's stated position on a single topic."""

    topic: str               # taxonomy key e.g. "housing"
    summary: str             # 1-2 sentence factual summary of stated position
    quote: str | None        # direct quote if available
    quote_source: str | None # URL to original quote
    source_url: str          # where this position was found


class CandidateDetail(BaseModel):
    """Full structured candidate profile."""

    id: str
    name: str
    party: str | None
    race_id: str
    bio: str | None
    photo_url: str | None
    website_url: str | None
    positions: dict[str, CandidatePosition]  # topic_key -> position
    ballotpedia_url: str | None
    sources: list[SourceCitation]
    data_completeness: DataCompleteness


class DonorSummary(BaseModel):
    """Single donor entry in campaign finance data."""

    name: str
    amount: float
    category: str | None   # "individual" | "PAC" | "corporation"


class IndustryDonation(BaseModel):
    """Industry-level aggregation of campaign donations."""

    industry: str
    amount: float
    pct_of_total: float


class CampaignFinanceSummary(BaseModel):
    """Campaign finance summary for a candidate or measure campaign."""

    entity_id: str
    entity_type: str              # "candidate" | "measure"
    total_raised: float | None
    total_spent: float | None
    top_donors: list[DonorSummary]          # top 5 max
    industry_breakdown: list[IndustryDonation] | None
    reporting_period: str | None
    sources: list[SourceCitation]
    data_completeness: DataCompleteness


# ---------------------------------------------------------------------------
# legislation-mcp output models
# ---------------------------------------------------------------------------


class MeasureText(BaseModel):
    """Raw legal text of a ballot measure fetched from an official source."""

    measure_id: str
    raw_text: str
    source_url: str
    source_type: str   # "html" | "pdf"
    fetched_at: str    # ISO 8601
    cache_hit: bool


class MeasureSection(BaseModel):
    """A labelled section of parsed ballot measure legal text."""

    label: str           # "findings" | "provisions" | "fiscal_impact" |
                         # "effective_date" | "definitions" | "other"
    heading: str | None  # original heading text if present
    content: str         # section text
    order: int           # position in document


class ParsedMeasureText(BaseModel):
    """Deterministically parsed and labelled sections of measure text."""

    measure_id: str
    sections: list[MeasureSection]


# ---------------------------------------------------------------------------
# news-mcp output models
# ---------------------------------------------------------------------------


class NewsArticle(BaseModel):
    """A single news article with optional bias metadata."""

    title: str
    url: str
    source_name: str
    published_at: str
    description: str | None   # article snippet, max 300 chars
    bias_rating: str | None   # from get_source_bias lookup
    bias_source: str | None   # "AllSides" | "AdFontes"


class NewsSearchResult(BaseModel):
    """Result set from a news search query."""

    articles: list[NewsArticle]
    query_used: str
    cache_hit: bool


class SourceBiasRating(BaseModel):
    """Political bias rating for a news domain."""

    domain: str
    bias_rating: str | None   # "Left" | "Lean Left" | "Center" | "Lean Right" | "Right"
    bias_source: str | None   # "AllSides" | "AdFontes"
    rating_url: str | None
    found: bool


# ---------------------------------------------------------------------------
# Input models for all tools
# ---------------------------------------------------------------------------


class GetBallotByAddressInput(BaseModel):
    """Input for the get_ballot_by_address tool."""

    address: str              # "123 Main St, Miami FL 33101" or "33101"
    election_id: str | None   # if None, uses next upcoming FL election


class GetMeasureDetailInput(BaseModel):
    """Input for the get_measure_detail tool."""

    measure_id: str
    include_full_text: bool = False


class GetCandidateDetailInput(BaseModel):
    """Input for the get_candidate_detail tool."""

    candidate_id: str
    topics: list[str] | None  # topic taxonomy keys to focus on; None = all


class GetCampaignFinanceInput(BaseModel):
    """Input for the get_campaign_finance tool."""

    entity_id: str    # candidate_id or measure_id
    entity_type: str  # "candidate" | "measure"


class GetMeasureTextInput(BaseModel):
    """Input for the get_measure_text tool."""

    measure_id: str
    state: str = "FL"


class ParseMeasureTextInput(BaseModel):
    """Input for the parse_measure_text tool."""

    measure_id: str
    raw_text: str


class SearchNewsInput(BaseModel):
    """Input for the search_news tool."""

    query: str
    date_from: str | None = None
    date_to: str | None = None
    max_results: int = 5


class GetSourceBiasInput(BaseModel):
    """Input for the get_source_bias tool."""

    domain: str  # e.g. "miamiherald.com"
