"""
Tool handler: parse_measure_text

Deterministically parses raw ballot measure legal text into labeled sections.

CRITICAL CONSTRAINTS — never violate:
  - NO LLM calls
  - NO external API calls
  - NO database access
  - NO caching (pure function — same input always produces same output)
  - Returns ParsedMeasureText for any input; never raises for valid input
"""

import re

from mcp_servers.shared.models import MeasureSection, ParsedMeasureText, ParseMeasureTextInput

# ---------------------------------------------------------------------------
# Section keyword map — ordered by priority (first match wins)
# ---------------------------------------------------------------------------

_KEYWORD_LABELS: list[tuple[str, str]] = [
    ("BE IT ENACTED", "provisions"),
    ("FISCAL IMPACT", "fiscal_impact"),
    ("EFFECTIVE DATE", "effective_date"),
    ("DEFINITIONS", "definitions"),
    ("LEGISLATIVE FINDINGS", "findings"),
    ("FINDINGS AND INTENT", "findings"),
    ("WHEREAS", "findings"),
]

_NUMBERED_RE = re.compile(r"^(§\s*\d+|SECTION\s+\d+|\d+\.)\s", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Public handler
# ---------------------------------------------------------------------------


def handle_parse_measure_text(inp: ParseMeasureTextInput) -> ParsedMeasureText:
    """
    Parse raw legal text into labeled sections. Pure deterministic function.

    Always returns a ParsedMeasureText with at least one section.
    No LLM, no external calls, no database, no caching.
    """
    sections = _parse_into_sections(inp.raw_text)
    return ParsedMeasureText(measure_id=inp.measure_id, sections=sections)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _parse_into_sections(raw_text: str) -> list[MeasureSection]:
    """Split text into labeled MeasureSection objects using keyword matching."""
    if not raw_text.strip():
        return [MeasureSection(label="other", heading=None, content="", order=0)]

    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    sections: list[MeasureSection] = []
    current_label = "other"
    current_heading: str | None = None
    current_lines: list[str] = []
    order = 0

    for line in lines:
        new_label = _classify_line(line)
        if new_label is not None:
            if current_lines or not sections:
                sections.append(MeasureSection(
                    label=current_label,
                    heading=current_heading,
                    content=" ".join(current_lines),
                    order=order,
                ))
                order += 1
            current_label = new_label
            current_heading = line[:80]
            current_lines = []
        else:
            current_lines.append(line)

    # Flush the final accumulated section
    sections.append(MeasureSection(
        label=current_label,
        heading=current_heading,
        content=" ".join(current_lines),
        order=order,
    ))

    return sections


def _classify_line(line: str) -> str | None:
    """
    Return the section label if this line starts a new section, else None.

    Priority order:
    1. Specific keyword phrases (highest priority)
    2. Numbered sections (§ N, SECTION N, N.)
    3. ALL-CAPS lines with ≥3 alpha characters
    4. Everything else → None (continues current section)
    """
    upper = line.upper()

    for keyword, label in _KEYWORD_LABELS:
        if keyword in upper:
            return label

    if _NUMBERED_RE.match(line):
        return "provisions"

    alpha_count = sum(c.isalpha() for c in line)
    if line == upper and alpha_count >= 3:
        return "other"

    return None
