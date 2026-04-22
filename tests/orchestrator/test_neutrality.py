"""
Slice 6 — neutrality validation for the Gemini-backed orchestrator.

Two tests live here:

  * ``test_neutrality_live`` — hits real Gemini (requires ``GEMINI_API_KEY``),
    runs the full orchestrator against each seed ballot, asserts neutrality
    rules, and writes a golden ``BallotReport`` JSON fixture.

  * ``test_neutrality_golden`` — loads the committed golden fixtures and
    re-runs the neutrality assertions. No API calls — catches future drift
    cheaply.

Both tests use the same ``_assert_neutrality`` helper so the contract is
checked identically whether the report is freshly generated or loaded from
disk.

The rules enforced:
  1. No forbidden output fields anywhere (``recommendation``,
     ``suggested_vote``, ``lean``, ``preferred_candidate``, ``vote_for``)
  2. No forbidden phrases in ``relevance_reason`` (the six phrases from
     ``relevance_ranker._FORBIDDEN_PHRASES``)
  3. Every measure has non-empty ``proponent_argument`` AND
     ``opponent_argument``
  4. Every measure has a non-empty ``sources`` list
  5. Every candidate has a non-empty ``sources`` list
"""

import os
import sqlite3
from pathlib import Path

import pytest

from apps.api.db.connection import run_migrations
from apps.api.orchestrator.events import ReportCompleteEvent
from apps.api.orchestrator.runner import run_orchestrator
from apps.api.orchestrator.schemas import BallotReport
from apps.api.orchestrator.stages.relevance_ranker import _FORBIDDEN_PHRASES
from scripts.seed_2024 import seed_database as seed_fl_2024
from scripts.seed_historical import seed_database as seed_fl_2022

# ─────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────

_FORBIDDEN_FIELDS: tuple[str, ...] = (
    "recommendation",
    "suggested_vote",
    "lean",
    "preferred_candidate",
    "vote_for",
)

_GOLDEN_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "llm" / "golden"

# Each tuple: (election_id, zip_code, priorities, display_name)
_SEED_BALLOTS: list[tuple[str, str, list[str], str]] = [
    ("FL-2022-GEN", "33101", ["housing", "education"], "Maria"),
    ("FL-2024-GEN", "33101", ["healthcare", "taxes"], "Jordan"),
]


# ─────────────────────────────────────────────
# Helpers (shared by both tests)
# ─────────────────────────────────────────────


def _assert_no_forbidden_fields(report: BallotReport) -> None:
    """Serialize the full report and check no forbidden field keys appear."""
    blob = report.model_dump_json().lower()
    for field in _FORBIDDEN_FIELDS:
        assert f'"{field}"' not in blob, (
            f"forbidden field {field!r} present in report JSON"
        )


def _assert_no_forbidden_phrases(report: BallotReport) -> None:
    """Check every relevance_reason for banned 'helpful' phrasing."""
    for item in report.items:
        reason_lc = item.relevance_reason.lower()
        for phrase in _FORBIDDEN_PHRASES:
            assert phrase not in reason_lc, (
                f"forbidden phrase {phrase!r} in relevance_reason: "
                f"{item.relevance_reason!r}"
            )


def _assert_balanced_measures(report: BallotReport) -> None:
    """Every measure must render both proponent and opponent arguments with sources."""
    for item in report.items:
        m = item.measure
        if m is None:
            continue
        assert m.proponent_argument.strip(), (
            f"measure {m.measure_id} missing proponent_argument"
        )
        assert m.opponent_argument.strip(), (
            f"measure {m.measure_id} missing opponent_argument"
        )
        assert m.sources, f"measure {m.measure_id} has empty sources"


def _assert_candidate_sources(report: BallotReport) -> None:
    """Every candidate must carry at least one source."""
    for item in report.items:
        r = item.race
        if r is None:
            continue
        for cand in r.candidates:
            assert cand.sources, (
                f"candidate {cand.candidate_id} in race {r.race_id} "
                "has empty sources"
            )


def _assert_neutrality(report: BallotReport) -> None:
    """Composite — run every neutrality rule against a fully-assembled report."""
    _assert_no_forbidden_fields(report)
    _assert_no_forbidden_phrases(report)
    _assert_balanced_measures(report)
    _assert_candidate_sources(report)


async def _prepare_db(db_path: str) -> None:
    """Migrate + seed both FL-2022 and FL-2024 historical elections."""
    await run_migrations(db_path)
    await seed_fl_2022(db_path)
    await seed_fl_2024(db_path)


def _preseed_session(db_path: str, session_id: str, election_id: str) -> None:
    """Insert a session row with ballot_id set so ballot_resolver locks to this election.

    Uses a sync sqlite3 connection — this runs inside async tests but the
    insert is trivial and async isn't needed here.
    """
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO sessions (id, status, ballot_id) VALUES (?, ?, ?)",
            (session_id, "active", election_id),
        )
        conn.commit()


async def _run_and_collect_report(
    session_id: str, message: str, db_path: str,
) -> BallotReport:
    """Drive the orchestrator to completion and return the final BallotReport."""
    report: BallotReport | None = None
    async for event in run_orchestrator(session_id, message, db_path):
        if isinstance(event, ReportCompleteEvent):
            report = event.report
    assert report is not None, "orchestrator did not emit a ReportCompleteEvent"
    return report


# ─────────────────────────────────────────────
# Helper unit tests (exercise the assertion helpers without live API)
# ─────────────────────────────────────────────


def _build_fixture_report() -> BallotReport:
    """Build a minimal, fully-valid BallotReport for helper unit tests."""
    from apps.api.orchestrator.schemas import (
        BallotReportItem,
        CandidateAnalysis,
        ElectionSummary,
        MeasureAnalysis,
        PrecinctInfo,
        RaceAnalysis,
        SourceCitation,
    )

    src = SourceCitation(
        name="Official FL Voter Guide",
        url="https://example.com/fl",
        bias_rating=None,
        fetched_at="2026-03-01T00:00:00Z",
    )
    measure = MeasureAnalysis(
        measure_id="M1",
        short_title="Amendment 1",
        plain_english_summary="Test summary.",
        what_yes_means="Yes effect.",
        what_no_means="No effect.",
        fiscal_impact=None,
        fiscal_impact_source=None,
        proponent_argument="Pro argument.",
        opponent_argument="Con argument.",
        proponent_source="https://example.com/pro",
        opponent_source="https://example.com/con",
        topic_tags=["housing"],
        data_completeness="full",
        sources=[src],
    )
    candidate = CandidateAnalysis(
        candidate_id="C1",
        name="Alice",
        party="Independent",
        bio_summary="Bio.",
        positions={"housing": "Supports more housing."},
        top_donors=["ACME ($100)"],
        funding_total="$1 raised",
        sources=[src],
    )
    race = RaceAnalysis(
        race_id="R1",
        race_title="Governor",
        race_type="state",
        candidates=[candidate],
        data_completeness="full",
        sources=[src],
    )
    return BallotReport(
        session_id="sess-unit",
        generated_at="2026-03-01T00:00:00Z",
        election=ElectionSummary(
            id="FL-2022-GEN",
            name="2022 FL General",
            date="2022-11-08",
            state="FL",
        ),
        precinct=PrecinctInfo(county="Miami-Dade", district=None, precinct_id=None),
        user_priorities=["housing"],
        items=[
            BallotReportItem(
                item_type="measure",
                relevance_score=8,
                relevance_reason="Relates to housing supply.",
                matched_priorities=["housing"],
                measure=measure,
                race=None,
            ),
            BallotReportItem(
                item_type="race",
                relevance_score=5,
                relevance_reason="Statewide executive race.",
                matched_priorities=[],
                measure=None,
                race=race,
            ),
        ],
    )


def test_assert_neutrality_passes_on_clean_report() -> None:
    _assert_neutrality(_build_fixture_report())


def test_assert_neutrality_fails_on_empty_proponent() -> None:
    report = _build_fixture_report()
    report.items[0].measure.proponent_argument = ""  # type: ignore[union-attr]
    with pytest.raises(AssertionError, match="proponent_argument"):
        _assert_balanced_measures(report)


def test_assert_neutrality_fails_on_empty_opponent() -> None:
    report = _build_fixture_report()
    report.items[0].measure.opponent_argument = "   "  # type: ignore[union-attr]
    with pytest.raises(AssertionError, match="opponent_argument"):
        _assert_balanced_measures(report)


def test_assert_neutrality_fails_on_empty_measure_sources() -> None:
    report = _build_fixture_report()
    report.items[0].measure.sources = []  # type: ignore[union-attr]
    with pytest.raises(AssertionError, match="empty sources"):
        _assert_balanced_measures(report)


def test_assert_neutrality_fails_on_empty_candidate_sources() -> None:
    report = _build_fixture_report()
    report.items[1].race.candidates[0].sources = []  # type: ignore[union-attr]
    with pytest.raises(AssertionError, match="empty sources"):
        _assert_candidate_sources(report)


@pytest.mark.parametrize("phrase", list(_FORBIDDEN_PHRASES))
def test_assert_neutrality_fails_on_forbidden_phrase(phrase: str) -> None:
    report = _build_fixture_report()
    report.items[0].relevance_reason = f"This will {phrase} find affordable rent."
    with pytest.raises(AssertionError, match="forbidden phrase"):
        _assert_no_forbidden_phrases(report)


@pytest.mark.parametrize("field", _FORBIDDEN_FIELDS)
def test_assert_neutrality_fails_on_forbidden_field(field: str) -> None:
    # Use a duck-typed stub so we can control the serialized JSON directly.
    # A real BallotReport cannot produce these keys because its schema forbids
    # them, so we exercise the assertion on a raw JSON blob instead.
    class _StubReport:
        def model_dump_json(self) -> str:
            return f'{{"items": [{{"{field}": "leak"}}]}}'

    with pytest.raises(AssertionError, match="forbidden field"):
        _assert_no_forbidden_fields(_StubReport())  # type: ignore[arg-type]


# ─────────────────────────────────────────────
# Live test — hits real Gemini, writes golden fixtures
# ─────────────────────────────────────────────


@pytest.mark.neutrality
@pytest.mark.parametrize(
    "election_id,zip_code,priorities,display_name",
    _SEED_BALLOTS,
    ids=[b[0] for b in _SEED_BALLOTS],
)
async def test_neutrality_live(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    election_id: str,
    zip_code: str,
    priorities: list[str],
    display_name: str,
) -> None:
    """Run the real orchestrator against a seed ballot with live Gemini.

    Side effect: writes ``tests/fixtures/llm/golden/{election_id}.json`` when
    assertions pass. That file is the baseline for
    ``test_neutrality_golden``.
    """
    # Gate: the slice spec requires running with MOCK_LLM=false and a real
    # GEMINI_API_KEY. Default test environments set GEMINI_API_KEY to a
    # placeholder, so checking the key alone is not enough — we also require
    # MOCK_LLM to be explicitly "false" at the process level as the opt-in
    # signal. The developer runs:  MOCK_LLM=false GEMINI_API_KEY=... pytest -m neutrality
    if os.environ.get("MOCK_LLM", "true").lower() != "false":
        pytest.skip(
            "Live neutrality run requires MOCK_LLM=false in the environment "
            "(opt-in signal) with a real GEMINI_API_KEY."
        )
    if not os.environ.get("GEMINI_API_KEY") or os.environ.get(
        "GEMINI_API_KEY", ""
    ).startswith("test"):
        pytest.skip(
            "Live neutrality run requires a real GEMINI_API_KEY (not a test placeholder)."
        )

    monkeypatch.setenv("MOCK_LLM", "false")
    monkeypatch.setenv("MOCK_EXTERNAL_APIS", "true")

    db_path = str(tmp_path / "neutrality.db")
    await _prepare_db(db_path)
    session_id = f"neutrality-{election_id}"
    _preseed_session(db_path, session_id, election_id)

    message = (
        f"I live in {zip_code}. My priorities are "
        f"{', '.join(priorities)}. My name is {display_name}."
    )
    report = await _run_and_collect_report(session_id, message, db_path)

    _assert_neutrality(report)

    _GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    (_GOLDEN_DIR / f"{election_id}.json").write_text(
        report.model_dump_json(indent=2), encoding="utf-8",
    )


# ─────────────────────────────────────────────
# Golden-fixture regression test — runs in default pytest
# ─────────────────────────────────────────────


_GOLDEN_FILES = sorted(_GOLDEN_DIR.glob("*.json")) if _GOLDEN_DIR.exists() else []


@pytest.mark.parametrize(
    "golden",
    _GOLDEN_FILES
    if _GOLDEN_FILES
    else [
        pytest.param(
            None,
            marks=pytest.mark.skip(
                reason=(
                    "No golden fixtures yet — run `pytest -m neutrality` with "
                    "GEMINI_API_KEY first to generate them."
                ),
            ),
        )
    ],
    ids=[p.stem for p in _GOLDEN_FILES] if _GOLDEN_FILES else ["no-fixtures"],
)
def test_neutrality_golden(golden: Path | None) -> None:
    """Load each committed golden fixture and re-assert neutrality."""
    assert golden is not None  # guarded by skip marker above
    report = BallotReport.model_validate_json(golden.read_text(encoding="utf-8"))
    _assert_neutrality(report)
