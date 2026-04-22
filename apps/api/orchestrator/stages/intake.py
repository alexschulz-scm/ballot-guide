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
    return _post_process(result)


def _post_process(result: IntakeResult) -> IntakeResult:
    """Validate zip_code format; set needs_clarification if invalid."""
    zip_code = result.zip_code.strip().replace(" ", "")
    if not _ZIP_RE.match(zip_code):
        logger.warning("Invalid zip_code from Claude: %r — setting needs_clarification", zip_code)
        return result.model_copy(update={
            "needs_clarification": True,
            "clarification_question": (
                result.clarification_question
                or "Could you please provide your 5-digit zip code?"
            ),
        })
    return result.model_copy(update={"zip_code": zip_code})
