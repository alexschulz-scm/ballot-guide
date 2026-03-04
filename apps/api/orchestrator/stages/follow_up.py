"""
Follow-up handler — answers user questions about an existing report.

Called by the runner when a session already has a completed report and
the user sends another message (e.g., "tell me more about Amendment 3").
"""

import json
import logging

from apps.api.orchestrator.claude_client import call_claude, load_prompt

logger = logging.getLogger(__name__)


async def run_follow_up(
    message: str,
    history: list[dict],
    report_json: str,
) -> str:
    """
    Calls Claude with the existing report context and the user's question.
    Returns the assistant's plain-text response.
    """
    system_prompt = load_prompt("system")
    formatted = (
        load_prompt("follow_up")
        .replace("{report_json}", _trim_report(report_json))
        .replace("{history}", json.dumps(history, ensure_ascii=False))
        .replace("{message}", message)
    )
    messages = [{"role": "user", "content": formatted}]
    return await call_claude(system_prompt, messages, max_tokens=600)


def _trim_report(report_json: str, max_chars: int = 12_000) -> str:
    """Truncate report JSON to stay within token budget."""
    if len(report_json) <= max_chars:
        return report_json
    return report_json[:max_chars] + "\n... (truncated)"
