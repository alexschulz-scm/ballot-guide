"""
Stage 3a: Measure Analyst — fetch data and analyze one ballot measure via Claude.
"""
import logging

from apps.api.orchestrator.claude_client import (
    SchemaValidationError,
    call_claude,
    load_prompt,
    parse_json_response,
)
from apps.api.orchestrator.schemas import MeasureAnalysis
from mcp_servers.ballot_data.tools.measure import handle_get_measure_detail
from mcp_servers.legislation.tools.measure_text import handle_get_measure_text
from mcp_servers.legislation.tools.parse_text import handle_parse_measure_text
from mcp_servers.news.tools.search import handle_search_news
from mcp_servers.shared.models import (
    GetMeasureDetailInput,
    GetMeasureTextInput,
    MeasureSummary,
    ParseMeasureTextInput,
    SearchNewsInput,
    ToolError,
)

logger = logging.getLogger(__name__)


async def run_measure_analysis(
    measure_summary: MeasureSummary,
    user_priorities: list[str],
    db_path: str,
) -> MeasureAnalysis | None:
    """
    Fetches measure detail, legislation text, parsed sections, and news.
    Calls Claude with measure_analysis.txt prompt. Retries up to 3 attempts
    on schema validation failure. Returns None after all retries fail.
    ToolError from any MCP tool degrades gracefully (empty data to Claude).
    """
    data = _fetch_measure_data(measure_summary, db_path)
    system_prompt = load_prompt("system")
    stage_prompt = load_prompt("measure_analysis")
    formatted = (
        stage_prompt
        .replace("{measure_data}", data["measure_data"])
        .replace("{legislation_sections}", data["legislation_sections"])
        .replace("{news_articles}", data["news_articles"])
    )
    messages = [{"role": "user", "content": formatted}]
    response = ""

    for attempt in range(3):
        try:
            response = await call_claude(system_prompt, messages, max_tokens=1200)
            return await parse_json_response(response, MeasureAnalysis)
        except SchemaValidationError as exc:
            if attempt == 2:
                logger.error("All retries failed for measure %s: %s", measure_summary.id, exc)
                return None
            messages.append({"role": "assistant", "content": response})
            messages.append({
                "role": "user",
                "content": f"Your response had this error: {exc}. Return valid JSON.",
            })
    return None  # unreachable but satisfies type checker


def _fetch_measure_data(measure: MeasureSummary, db_path: str) -> dict:
    """Fetch all MCP data for a measure; degrade gracefully on ToolError."""
    detail = handle_get_measure_detail(
        GetMeasureDetailInput(measure_id=measure.id), db_path
    )
    measure_data = detail.model_dump_json() if not isinstance(detail, ToolError) else "{}"

    text_result = handle_get_measure_text(
        GetMeasureTextInput(measure_id=measure.id), db_path
    )
    if isinstance(text_result, ToolError):
        legislation_sections = "[]"
    else:
        parsed = handle_parse_measure_text(
            ParseMeasureTextInput(measure_id=measure.id, raw_text=text_result.raw_text)
        )
        legislation_sections = parsed.model_dump_json()

    news = handle_search_news(
        SearchNewsInput(query=f"Florida {measure.short_title}"), db_path
    )
    news_articles = news.model_dump_json() if not isinstance(news, ToolError) else "[]"

    return {
        "measure_data": measure_data,
        "legislation_sections": legislation_sections,
        "news_articles": news_articles,
    }
