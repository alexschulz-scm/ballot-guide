"""
Stage 3b: Candidate Analyst — fetch data and analyze all candidates in one race.
"""
import logging
from datetime import datetime, timezone

from apps.api.orchestrator.llm_client import (
    SchemaValidationError,
    call_llm,
    load_prompt,
    parse_json_response,
)
from apps.api.orchestrator.schemas import CandidateAnalysis, RaceAnalysis, SourceCitation
from mcp_servers.ballot_data.tools.candidate import handle_get_candidate_detail
from mcp_servers.ballot_data.tools.finance import handle_get_campaign_finance
from mcp_servers.news.tools.search import handle_search_news
from mcp_servers.shared.models import (
    GetCampaignFinanceInput,
    GetCandidateDetailInput,
    RaceSummary,
    SearchNewsInput,
    ToolError,
)

logger = logging.getLogger(__name__)


async def run_candidate_analysis(
    race: RaceSummary,
    user_priorities: list[str],
    db_path: str,
) -> RaceAnalysis | None:
    """
    Analyzes all candidates in a race sequentially.
    Returns RaceAnalysis if at least one candidate succeeded.
    Returns None only if ALL candidates fail.
    data_completeness: 'full' if all succeeded, 'partial' if some failed.
    """
    analyses: list[CandidateAnalysis] = []
    for candidate_id in race.candidate_ids:
        result = await _analyze_one_candidate(
            candidate_id, race.id, user_priorities, db_path
        )
        if result is not None:
            analyses.append(result)

    if not analyses:
        logger.error("All candidates failed for race %s", race.id)
        return None

    completeness = "full" if len(analyses) == len(race.candidate_ids) else "partial"
    return RaceAnalysis(
        race_id=race.id,
        race_title=race.title,
        race_type=race.type,
        candidates=analyses,
        data_completeness=completeness,
        sources=_collect_race_sources(analyses),
    )


def _fetch_candidate_data(candidate_id, user_priorities, db_path):
    """Fetch MCP data for a single candidate."""
    detail = handle_get_candidate_detail(
        GetCandidateDetailInput(candidate_id=candidate_id, topics=user_priorities), db_path
    )
    finance = handle_get_campaign_finance(
        GetCampaignFinanceInput(entity_id=candidate_id, entity_type="candidate"), db_path
    )
    name = detail.name if not isinstance(detail, ToolError) else candidate_id
    news = handle_search_news(
        SearchNewsInput(query=f"Florida {name}"), db_path
    )
    return (
        detail.model_dump_json() if not isinstance(detail, ToolError) else "{}",
        finance.model_dump_json() if not isinstance(finance, ToolError) else "{}",
        news.model_dump_json() if not isinstance(news, ToolError) else "[]",
        news if not isinstance(news, ToolError) else None,
    )


async def _analyze_one_candidate(
    candidate_id: str, race_id: str,
    user_priorities: list[str], db_path: str,
) -> CandidateAnalysis | None:
    """Fetch MCP data and call Claude for a single candidate."""
    cand_data, fin_data, news_data, news_result = _fetch_candidate_data(
        candidate_id, user_priorities, db_path
    )
    system_prompt = load_prompt("system")
    formatted = (
        load_prompt("candidate_analysis")
        .replace("{user_priorities}", ", ".join(user_priorities))
        .replace("{candidate_data}", cand_data)
        .replace("{finance_data}", fin_data)
        .replace("{news_articles}", news_data)
    )
    messages = [{"role": "user", "content": formatted}]
    response = ""

    for attempt in range(3):
        try:
            response = await call_llm(system_prompt, messages, max_tokens=2000, response_schema=CandidateAnalysis)
            result = await parse_json_response(response, CandidateAnalysis)
            _ensure_news_sources(result, news_result)
            return result
        except SchemaValidationError as exc:
            if attempt == 2:
                logger.error("All retries failed for candidate %s: %s", candidate_id, exc)
                return None
            messages.append({"role": "assistant", "content": response})
            messages.append({
                "role": "user",
                "content": f"Your response had this error: {exc}. Return valid JSON.",
            })
    return None


def _collect_race_sources(analyses: list[CandidateAnalysis]) -> list[SourceCitation]:
    """Flatten and deduplicate sources across all candidate analyses."""
    seen: set[str] = set()
    sources: list[SourceCitation] = []
    for analysis in analyses:
        for src in analysis.sources:
            if src.url not in seen:
                seen.add(src.url)
                sources.append(src)
    return sources


def _ensure_news_sources(analysis: CandidateAnalysis, news_result) -> None:
    """Append news articles as SourceCitations if Claude omitted them."""
    if news_result is None:
        return
    existing_urls = {s.url for s in analysis.sources}
    now = datetime.now(timezone.utc).isoformat()
    for article in news_result.articles:
        if article.url not in existing_urls:
            analysis.sources.append(SourceCitation(
                name=article.source_name,
                url=article.url,
                bias_rating=article.bias_rating,
                bias_source=article.bias_source,
                bias_rating_url=None,
                fetched_at=now,
            ))
            existing_urls.add(article.url)
