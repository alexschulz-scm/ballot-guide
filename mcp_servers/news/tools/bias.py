"""
Tool handler: get_source_bias

Looks up political bias rating for a news source domain using a bundled
JSON file of AllSides ratings.

CRITICAL CONSTRAINTS — never violate:
  - NO ToolError (ever) — unknown domains return SourceBiasRating(found=False)
  - NO external API calls
  - NO database access
  - Module-level cache to avoid repeated file reads
"""

import json
from pathlib import Path

from mcp_servers.shared.models import GetSourceBiasInput, SourceBiasRating

# ---------------------------------------------------------------------------
# Module-level ratings cache — populated on first call
# ---------------------------------------------------------------------------

_RATINGS_CACHE: dict | None = None


def _load_bias_ratings() -> dict:
    """Load bias_ratings.json into module-level cache on first call."""
    global _RATINGS_CACHE
    if _RATINGS_CACHE is None:
        ratings_path = Path(__file__).parent.parent / "bias_ratings.json"
        with ratings_path.open("r", encoding="utf-8") as fh:
            _RATINGS_CACHE = json.load(fh)
    return _RATINGS_CACHE


# ---------------------------------------------------------------------------
# Public handler
# ---------------------------------------------------------------------------


def handle_get_source_bias(inp: GetSourceBiasInput) -> SourceBiasRating:
    """
    Return bias rating for a news source domain.

    Always returns SourceBiasRating — never ToolError.
    Unknown domains return found=False with null rating fields.
    """
    domain = inp.domain.lower().strip().lstrip("www.")
    ratings = _load_bias_ratings()
    entry = ratings.get(domain)

    if entry:
        return SourceBiasRating(
            domain=inp.domain,
            bias_rating=entry["bias_rating"],
            bias_source=entry["bias_source"],
            rating_url=entry.get("rating_url"),
            found=True,
        )

    return SourceBiasRating(
        domain=inp.domain,
        bias_rating=None,
        bias_source=None,
        rating_url=None,
        found=False,
    )
