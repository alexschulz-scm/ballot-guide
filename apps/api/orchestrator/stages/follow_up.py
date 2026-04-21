"""
Follow-up handler — answers user questions about an existing report.

Called by the runner when a session already has a completed report and
the user sends another message (e.g., "tell me more about Amendment 3").

Enhanced: detects intent and fetches deeper data via MCP when needed.
"""

import json
import logging
import re

from mcp_servers.shared.models import ToolError

from apps.api.orchestrator.llm_client import call_llm, load_prompt

logger = logging.getLogger(__name__)

# Intent types returned by _detect_follow_up_intent
_INTENT_DETAIL = "detail"
_INTENT_FINANCE = "finance"
_INTENT_NEWS = "news"
_INTENT_LEGAL_TEXT = "legal_text"
_INTENT_CIVICS = "civics"
_INTENT_GENERAL = "general"


async def run_follow_up(
    message: str,
    history: list[dict],
    report_json: str,
    db_path: str,
) -> tuple[str, list[str]]:
    """
    Enhanced follow-up: detect intent, fetch deeper data if needed, answer.

    Returns (answer_text, sources_used) where sources_used is a list of
    MCP tool names that were called (empty if report-only).
    """
    item_id, intent = _detect_follow_up_intent(message, report_json)

    extra_context = ""
    sources_used: list[str] = []
    if item_id and intent in (_INTENT_DETAIL, _INTENT_FINANCE,
                               _INTENT_NEWS, _INTENT_LEGAL_TEXT):
        extra_context, sources_used = await _fetch_deeper_data(
            item_id, intent, report_json, db_path,
        )

    system_prompt = load_prompt("system")
    formatted = (
        load_prompt("follow_up")
        .replace("{report_json}", _trim_report(report_json))
        .replace("{extra_context}", extra_context)
        .replace("{history}", json.dumps(history, ensure_ascii=False))
        .replace("{message}", message)
    )
    messages = [{"role": "user", "content": formatted}]
    answer = await call_llm(system_prompt, messages, max_tokens=1000)
    return answer, sources_used


def _detect_follow_up_intent(
    message: str, report_json: str,
) -> tuple[str | None, str]:
    """
    Parse user message to determine which ballot item they're asking about
    and what kind of deeper info they want.

    Returns (item_id | None, intent_type).
    """
    msg_lower = message.lower()

    # Civics keywords — no item needed
    civics_keywords = [
        "what is a ", "what's a ", "what does ", "how does ",
        "constitutional amendment", "judicial retention",
        "ballot measure", "how do elections", "what happens if",
        "difference between", "primary vs", "general election",
    ]
    if any(kw in msg_lower for kw in civics_keywords):
        return None, _INTENT_CIVICS

    # Try to match a ballot item from the report
    item_id = _match_item_from_report(msg_lower, report_json)

    # Finance keywords
    finance_keywords = [
        "fund", "donor", "money", "financ", "contribut",
        "spending", "raised", "pac", "super pac",
    ]
    if any(kw in msg_lower for kw in finance_keywords):
        return item_id, _INTENT_FINANCE

    # Legal text / full text keywords
    text_keywords = [
        "full text", "legal text", "actual text", "exact word",
        "what does it say", "read the amendment", "ballot language",
    ]
    if any(kw in msg_lower for kw in text_keywords):
        return item_id, _INTENT_LEGAL_TEXT

    # News keywords
    news_keywords = [
        "news", "coverage", "media", "article", "report",
        "what are people saying", "press",
    ]
    if any(kw in msg_lower for kw in news_keywords):
        return item_id, _INTENT_NEWS

    # Detail keywords (catch-all for "tell me more")
    detail_keywords = [
        "more about", "tell me about", "explain", "detail",
        "deeper", "elaborate", "more on",
    ]
    if item_id and any(kw in msg_lower for kw in detail_keywords):
        return item_id, _INTENT_DETAIL

    return item_id, _INTENT_GENERAL


def _match_item_from_report(
    msg_lower: str, report_json: str,
) -> str | None:
    """Find the first ballot item ID whose title appears in the message."""
    try:
        report = json.loads(report_json)
    except (json.JSONDecodeError, TypeError):
        return None

    for item in report.get("items", []):
        if item.get("measure"):
            title = item["measure"].get("short_title", "")
            measure_id = item["measure"].get("measure_id", "")
            if _title_matches(msg_lower, title):
                return measure_id
        if item.get("race"):
            title = item["race"].get("race_title", "")
            race_id = item["race"].get("race_id", "")
            if _title_matches(msg_lower, title):
                return race_id
            # Also match candidate names
            for cand in item["race"].get("candidates", []):
                if cand.get("name", "").lower() in msg_lower:
                    return race_id
    return None


def _title_matches(msg_lower: str, title: str) -> bool:
    """Check if any significant part of the title appears in the message."""
    if not title:
        return False
    title_lower = title.lower()
    if title_lower in msg_lower:
        return True
    # Match "amendment N" pattern
    amend_match = re.search(r"amendment\s+(\d+)", title_lower)
    if amend_match and f"amendment {amend_match.group(1)}" in msg_lower:
        return True
    # Match short keywords (e.g., "governor", "senate")
    for keyword in ["governor", "senate", "house", "attorney general"]:
        if keyword in title_lower and keyword in msg_lower:
            return True
    return False


async def _fetch_deeper_data(
    item_id: str, intent: str, report_json: str, db_path: str,
) -> tuple[str, list[str]]:
    """Fetch additional data via MCP tools based on intent."""
    sources_used: list[str] = []
    sections: list[str] = []

    if intent == _INTENT_LEGAL_TEXT:
        text = _fetch_measure_text(item_id, db_path)
        if text:
            sections.append(f"FULL MEASURE TEXT:\n{text}")
            sources_used.append("get_measure_text")

    elif intent == _INTENT_FINANCE:
        finance = _fetch_finance(item_id, report_json, db_path)
        if finance:
            sections.append(f"CAMPAIGN FINANCE DATA:\n{finance}")
            sources_used.append("get_campaign_finance")

    elif intent == _INTENT_NEWS:
        news = _fetch_news(item_id, report_json, db_path)
        if news:
            sections.append(f"RECENT NEWS COVERAGE:\n{news}")
            sources_used.append("search_news")

    elif intent == _INTENT_DETAIL:
        detail = _fetch_detail(item_id, db_path)
        if detail:
            sections.append(f"DETAILED DATA:\n{detail}")
            sources_used.append("get_detail")

    return "\n\n".join(sections), sources_used


def _fetch_measure_text(measure_id: str, db_path: str) -> str | None:
    """Fetch full legal text for a measure."""
    try:
        from mcp_servers.legislation.tools.measure_text import (
            handle_get_measure_text,
        )
        from mcp_servers.shared.models import GetMeasureTextInput

        result = handle_get_measure_text(
            GetMeasureTextInput(measure_id=measure_id), db_path,
        )
        if isinstance(result, ToolError):
            return None
        return result.model_dump_json(indent=2)
    except Exception:
        logger.exception("Failed to fetch measure text for %s", measure_id)
        return None


def _fetch_finance(
    item_id: str, report_json: str, db_path: str,
) -> str | None:
    """Fetch campaign finance for candidates in a race."""
    try:
        from mcp_servers.ballot_data.tools.finance import (
            handle_get_campaign_finance,
        )
        from mcp_servers.shared.models import GetCampaignFinanceInput

        report = json.loads(report_json)
        candidate_ids = _find_candidate_ids(item_id, report)
        if not candidate_ids:
            return None

        results = []
        for cid in candidate_ids:
            result = handle_get_campaign_finance(
                GetCampaignFinanceInput(
                    entity_id=cid, entity_type="candidate",
                ), db_path,
            )
            if not isinstance(result, ToolError):
                results.append(result.model_dump_json(indent=2))
        return "\n---\n".join(results) if results else None
    except Exception:
        logger.exception("Failed to fetch finance for %s", item_id)
        return None


def _fetch_news(
    item_id: str, report_json: str, db_path: str,
) -> str | None:
    """Search news for a ballot item."""
    try:
        from mcp_servers.news.tools.search import handle_search_news
        from mcp_servers.shared.models import SearchNewsInput

        report = json.loads(report_json)
        query = _find_item_title(item_id, report)
        if not query:
            return None

        result = handle_search_news(
            SearchNewsInput(query=f"Florida {query}", max_results=5),
            db_path,
        )
        if isinstance(result, ToolError):
            return None
        return result.model_dump_json(indent=2)
    except Exception:
        logger.exception("Failed to fetch news for %s", item_id)
        return None


def _fetch_detail(item_id: str, db_path: str) -> str | None:
    """Fetch detailed measure or candidate data."""
    try:
        from mcp_servers.ballot_data.tools.measure import (
            handle_get_measure_detail,
        )
        from mcp_servers.shared.models import GetMeasureDetailInput

        result = handle_get_measure_detail(
            GetMeasureDetailInput(
                measure_id=item_id, include_full_text=True,
            ), db_path,
        )
        if not isinstance(result, ToolError):
            return result.model_dump_json(indent=2)
    except Exception:
        logger.debug("Item %s not a measure, trying candidate", item_id)

    try:
        from mcp_servers.ballot_data.tools.candidate import (
            handle_get_candidate_detail,
        )
        from mcp_servers.shared.models import GetCandidateDetailInput

        result = handle_get_candidate_detail(
            GetCandidateDetailInput(candidate_id=item_id, topics=None), db_path,
        )
        if not isinstance(result, ToolError):
            return result.model_dump_json(indent=2)
    except Exception:
        logger.exception("Failed to fetch detail for %s", item_id)

    return None


def _find_candidate_ids(race_id: str, report: dict) -> list[str]:
    """Extract candidate IDs for a race from the report."""
    for item in report.get("items", []):
        race = item.get("race")
        if race and race.get("race_id") == race_id:
            return [c["candidate_id"] for c in race.get("candidates", [])]
    return []


def _find_item_title(item_id: str, report: dict) -> str | None:
    """Find an item's title in the report by ID."""
    for item in report.get("items", []):
        if item.get("measure") and item["measure"].get("measure_id") == item_id:
            return item["measure"].get("short_title")
        if item.get("race") and item["race"].get("race_id") == item_id:
            return item["race"].get("race_title")
    return None


def _trim_report(report_json: str, max_chars: int = 12_000) -> str:
    """Truncate report JSON to stay within token budget."""
    if len(report_json) <= max_chars:
        return report_json
    return report_json[:max_chars] + "\n... (truncated)"
