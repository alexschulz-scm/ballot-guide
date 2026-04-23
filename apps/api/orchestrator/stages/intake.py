"""
Stage 1: Intake — extract zip code and priorities from user message.
"""
import json
import logging
import re

from apps.api.orchestrator.llm_client import call_llm, load_prompt, parse_json_response
from apps.api.orchestrator.schemas import IntakeResult

logger = logging.getLogger(__name__)

_ZIP_RE = re.compile(r"^\d{5}$")


_PRIORITIES_ASK_MARKERS = ("priorities", "issues matter", "care about", "matter most")


async def run_intake(
    message: str,
    history: list[dict],
    db_path: str,
) -> IntakeResult:
    """
    Loads intake.txt prompt, calls Claude, returns normalized IntakeResult.
    db_path retained for interface consistency; not used in this stage.
    IntakeResult.priorities is already filtered to taxonomy by Pydantic validator.
    Post-processing: validates zip_code format; sets needs_clarification if invalid.
    """
    system_prompt = load_prompt("system")
    stage_prompt = load_prompt("intake")
    formatted = (
        stage_prompt
        .replace("{history}", json.dumps(history, ensure_ascii=False))
        .replace("{message}", message)
    )
    messages = [{"role": "user", "content": formatted}]
    response = await call_llm(system_prompt, messages, max_tokens=400, response_schema=IntakeResult)
    result = await parse_json_response(response, IntakeResult)
    return _post_process(result, history)


def _post_process(result: IntakeResult, history: list[dict]) -> IntakeResult:
    """Validate zip_code format and require priorities on first turn."""
    zip_code = result.zip_code.strip().replace(" ", "")
    if not _ZIP_RE.match(zip_code):
        logger.warning("Invalid zip_code from LLM: %r — setting needs_clarification", zip_code)
        return result.model_copy(update={
            "needs_clarification": True,
            "clarification_question": (
                result.clarification_question
                or "Could you please provide your 5-digit zip code?"
            ),
        })
    if (
        not result.needs_clarification
        and not result.priorities
        and not result.priorities_raw.strip()
        and not _already_asked_priorities(history)
    ):
        logger.info("No priorities provided and no prior ask — requesting clarification")
        return result.model_copy(update={
            "zip_code": zip_code,
            "needs_clarification": True,
            "clarification_question": (
                "Thanks! What issues matter most to you? For example: housing, "
                "education, healthcare, taxes, environment, public safety, economy, "
                "voting rights, infrastructure, or senior services. You can also say "
                "\"no preference\" to see everything."
            ),
        })
    return result.model_copy(update={"zip_code": zip_code})


def _already_asked_priorities(history: list[dict]) -> bool:
    """True if any assistant message in history already asked about priorities."""
    for msg in history:
        if msg.get("role") != "assistant":
            continue
        content = (msg.get("content") or "").lower()
        if any(marker in content for marker in _PRIORITIES_ASK_MARKERS):
            return True
    return False
