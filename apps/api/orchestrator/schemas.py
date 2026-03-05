"""
Orchestrator output schemas.

All Pydantic models produced by orchestrator stages. These are the data contracts
between stages and between the orchestrator and the API layer.

CRITICAL: BallotReport must NEVER contain recommendation, suggested_vote,
lean, preferred_candidate, or vote_for fields. See neutrality contract.

Names must match exactly — other files import by name.
"""

from pydantic import BaseModel, field_validator


# ---------------------------------------------------------------------------
# Canonical topic taxonomy (from CLAUDE.md)
# ---------------------------------------------------------------------------

_TOPIC_TAXONOMY: frozenset[str] = frozenset({
    "housing",
    "education",
    "taxes",
    "healthcare",
    "environment",
    "public_safety",
    "economy",
    "voting_rights",
    "infrastructure",
    "senior_services",
})


# ---------------------------------------------------------------------------
# Primitive shared types
# ---------------------------------------------------------------------------


class SourceCitation(BaseModel):
    """
    Source attribution for any claim in orchestrator output.

    Defined locally for layer independence from mcp_servers/shared/models.py.
    Structurally identical to the MCP SourceCitation — no DataSource alias.
    """

    name: str            # "Ballotpedia", "Miami Herald"
    url: str             # direct URL to the source record
    bias_rating: str | None       # AllSides rating if news source, else None
    bias_source: str | None = None      # "AllSides" | "AdFontes" | None
    bias_rating_url: str | None = None  # link to the rating page
    fetched_at: str      # ISO 8601


class ElectionSummary(BaseModel):
    """
    Top-level election context passed through from MCP BallotResponse.

    Integration note (Issue 1): defined here so BallotReport can reference it.
    Integration note (Issue 7): model field is "date"; DB column is "election_date".
    MCP server maps: ElectionSummary(date=row["election_date"], ...)
    """

    id: str     # "FL-2026-GEN"
    name: str   # "2026 Florida General Election"
    date: str   # "2026-11-03"
    state: str  # "FL"


class PrecinctInfo(BaseModel):
    """
    Voter's resolved precinct passed through from MCP BallotResponse.

    Integration note (Issue 1): defined here so BallotReport can reference it.
    """

    county: str
    district: str | None
    precinct_id: str | None


# ---------------------------------------------------------------------------
# Stage output models
# ---------------------------------------------------------------------------


class IntakeResult(BaseModel):
    """Stage 1 output: extracted zip code and priorities from user message."""

    zip_code: str                       # normalized 5-digit zip
    address_full: str | None            # full address if provided
    priorities: list[str]               # normalized taxonomy keys, max 5
    priorities_raw: str = ""            # original user text, preserved verbatim
    display_name: str | None            # user's name if provided, else None
    needs_clarification: bool           # True if zip/priorities couldn't be extracted
    clarification_question: str | None  # if needs_clarification, what to ask

    @field_validator("priorities")
    @classmethod
    def validate_priorities(cls, v: list[str]) -> list[str]:
        """Filter unknown topics, truncate to max 5. Silent — no ValidationError."""
        filtered = [p for p in v if p in _TOPIC_TAXONOMY]
        return filtered[:5]


class CandidateAnalysis(BaseModel):
    """
    Analysis of a single candidate.

    Integration note (Issue 3): positions are plain strings — the candidate_analyst
    stage flattens MCP CandidatePosition objects (.summary field) to str.
    Integration note (Issue 4): top_donors formatted as "Name ($Amount)" strings
    from MCP DonorSummary objects by the candidate_analyst stage.
    """

    candidate_id: str
    name: str
    party: str | None
    bio_summary: str | None      # max 75 words
    positions: dict[str, str]    # topic_key → 1-sentence position summary
    top_donors: list[str]        # max 3, formatted "Name ($Amount)"
    funding_total: str | None    # formatted "$1.2M raised"
    sources: list[SourceCitation]


class MeasureAnalysis(BaseModel):
    """Stage 3a output: full analysis of a ballot measure."""

    measure_id: str
    short_title: str
    plain_english_summary: str       # max 150 words, no legal jargon
    what_yes_means: str              # max 50 words: concrete effect of YES vote
    what_no_means: str               # max 50 words: concrete effect of NO vote
    fiscal_impact: str | None        # from official source only, max 100 words
    fiscal_impact_source: str | None
    proponent_argument: str          # max 100 words, strongest case for YES
    opponent_argument: str           # max 100 words, strongest case for NO
    proponent_source: str            # URL to official pro argument
    opponent_source: str             # URL to official con argument
    topic_tags: list[str]            # from MCP data, not re-generated
    data_completeness: str           # passed through from MCP response
    sources: list[SourceCitation]    # all sources used, min 1

    @field_validator("sources")
    @classmethod
    def validate_sources(cls, v: list[SourceCitation]) -> list[SourceCitation]:
        if not v:
            raise ValueError("MeasureAnalysis must have at least one source")
        return v


class RaceAnalysis(BaseModel):
    """Stage 3b output: analysis of all candidates in a race."""

    race_id: str
    race_title: str
    race_type: str
    candidates: list[CandidateAnalysis]
    data_completeness: str
    sources: list[SourceCitation]


class RelevanceScore(BaseModel):
    """Stage 4 output: relevance score for one ballot item."""

    item_id: str                     # measure_id or race_id
    item_type: str                   # "measure" | "race"
    relevance_score: int             # 1-10, 10 = most relevant
    relevance_reason: str            # max 30 words: topic connection only
    matched_priorities: list[str]    # which priorities this item matches

    @field_validator("relevance_score")
    @classmethod
    def validate_score(cls, v: int) -> int:
        if not 1 <= v <= 10:
            raise ValueError(f"relevance_score must be between 1 and 10, got {v}")
        return v


class BallotReportItem(BaseModel):
    """One item in the final ballot report, with relevance metadata."""

    item_type: str                   # "measure" | "race"
    relevance_score: int
    relevance_reason: str
    matched_priorities: list[str]
    measure: MeasureAnalysis | None  # populated if item_type == "measure"
    race: RaceAnalysis | None        # populated if item_type == "race"


class BallotReport(BaseModel):
    """
    Final output of the orchestrator — the complete voter ballot guide.

    FORBIDDEN FIELDS (neutrality contract — do not add):
      recommendation, suggested_vote, lean, preferred_candidate, vote_for
    """

    session_id: str
    generated_at: str                # ISO 8601
    election: ElectionSummary
    precinct: PrecinctInfo
    user_priorities: list[str]       # normalized taxonomy keys
    items: list[BallotReportItem]    # ordered by relevance_score descending
