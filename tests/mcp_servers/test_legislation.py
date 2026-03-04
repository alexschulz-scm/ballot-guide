"""
Tests for the legislation-mcp server tools.

All tests run offline — no real HTTP calls made.
Pure parse tests (1-5, 8) require no db_path or mock_env.
SQLite/cache tests (6-7) use the db_path fixture.
"""

import pytest

from mcp_servers.legislation.parsers.pdf_parser import extract_text_from_pdf
from mcp_servers.legislation.tools.measure_text import handle_get_measure_text
from mcp_servers.legislation.tools.parse_text import handle_parse_measure_text
from mcp_servers.shared.models import (
    GetMeasureTextInput,
    MeasureText,
    ParsedMeasureText,
    ParseMeasureTextInput,
)


# ---------------------------------------------------------------------------
# Test 1: Parse always produces at least one section
# ---------------------------------------------------------------------------


def test_parse_produces_at_least_one_section():
    """Any text input produces at least one section."""
    inp = ParseMeasureTextInput(
        measure_id="FL-2022-M1",
        raw_text="This is some basic legislative text with no special headings.",
    )
    result = handle_parse_measure_text(inp)
    assert isinstance(result, ParsedMeasureText)
    assert len(result.sections) >= 1


# ---------------------------------------------------------------------------
# Test 2: FISCAL IMPACT keyword → fiscal_impact label
# ---------------------------------------------------------------------------


def test_parse_fiscal_impact_keyword():
    """Text containing 'FISCAL IMPACT' yields a section with label fiscal_impact."""
    raw = (
        "Preamble text here.\n"
        "FISCAL IMPACT: Estimated $5M annual cost to the state.\n"
        "Additional details follow."
    )
    inp = ParseMeasureTextInput(measure_id="FL-2022-M1", raw_text=raw)
    result = handle_parse_measure_text(inp)
    labels = [s.label for s in result.sections]
    assert "fiscal_impact" in labels


# ---------------------------------------------------------------------------
# Test 3: BE IT ENACTED keyword → provisions label
# ---------------------------------------------------------------------------


def test_parse_be_it_enacted_keyword():
    """Text containing 'BE IT ENACTED' yields a section with label provisions."""
    raw = (
        "LEGISLATIVE FINDINGS: The legislature finds the following.\n"
        "BE IT ENACTED by the Legislature of the State of Florida:\n"
        "Section 1. The following shall apply."
    )
    inp = ParseMeasureTextInput(measure_id="FL-2022-M2", raw_text=raw)
    result = handle_parse_measure_text(inp)
    labels = [s.label for s in result.sections]
    assert "provisions" in labels


# ---------------------------------------------------------------------------
# Test 4: Unrecognized content gets labeled other
# ---------------------------------------------------------------------------


def test_parse_unrecognized_content_labeled_other():
    """Plain prose without keywords or numbering gets label 'other'."""
    inp = ParseMeasureTextInput(
        measure_id="FL-2022-M1",
        raw_text="This is plain text with no special structure at all.",
    )
    result = handle_parse_measure_text(inp)
    assert any(s.label == "other" for s in result.sections)


# ---------------------------------------------------------------------------
# Test 5: Empty input → exactly one section with label other, no exception
# ---------------------------------------------------------------------------


def test_parse_empty_input_returns_other_section():
    """Empty string yields exactly one section with label 'other'."""
    inp = ParseMeasureTextInput(measure_id="FL-2022-M1", raw_text="")
    result = handle_parse_measure_text(inp)
    assert isinstance(result, ParsedMeasureText)
    assert len(result.sections) == 1
    assert result.sections[0].label == "other"
    assert result.sections[0].content == ""


# ---------------------------------------------------------------------------
# Test 6: get_measure_text returns cache_hit=True on second call
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_measure_text_cache_hit(db_path, mock_env):
    """Second call for the same measure returns cache_hit=True."""
    inp = GetMeasureTextInput(measure_id="FL-2022-M2")

    first = handle_get_measure_text(inp, db_path)
    assert isinstance(first, MeasureText), f"Expected MeasureText, got: {first}"
    assert first.cache_hit is False

    second = handle_get_measure_text(inp, db_path)
    assert isinstance(second, MeasureText)
    assert second.cache_hit is True


# ---------------------------------------------------------------------------
# Test 7: get_measure_text reads from SQLite (no HTTP needed)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_measure_text_sqlite_primary(db_path, mock_env):
    """FL-2022-M2 has measure_text in the seed DB; returned without HTTP."""
    inp = GetMeasureTextInput(measure_id="FL-2022-M2")
    result = handle_get_measure_text(inp, db_path)
    assert isinstance(result, MeasureText)
    assert result.measure_id == "FL-2022-M2"
    assert result.source_url != ""
    assert len(result.raw_text) > 0


# ---------------------------------------------------------------------------
# Test 8: pdf_parser returns empty string for corrupt data
# ---------------------------------------------------------------------------


def test_pdf_parser_corrupt_returns_empty():
    """extract_text_from_pdf returns '' for invalid PDF data — never raises."""
    result = extract_text_from_pdf(b"not a pdf at all")
    assert result == ""
