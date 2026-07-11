"""Offline tests for the research adapter's groundedness measure->keep/discard loop.

Covers MECH-01: score each generated section against the fixture's
``retrieval_questions``, retry a weak section within a bounded budget, discard it
if still weak — a measurement over OUTPUT, never a prompt change. All tests are
offline (MagicMock bridge or dry-run); none require a live ``claude`` CLI.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from flowstate.bridge import BridgeResult
from flowstate.state import InterviewAnswers
from flowstate.tools.research import MOCK_REPORT, ResearchAdapter


def _write_fixture(root: Path, questions: list[str]) -> None:
    """Write a starter fixture with the given retrieval_questions."""
    fdir = root / ".planning" / "fixtures"
    fdir.mkdir(parents=True, exist_ok=True)
    (fdir / "starter.json").write_text(json.dumps({"retrieval_questions": questions}))


def _gen(output: str = "## Findings\n\nGrounded content.") -> BridgeResult:
    """A successful generation bridge result."""
    return BridgeResult(success=True, output=output, exit_code=0)


def _score(value: int) -> BridgeResult:
    """A scoring bridge result returning a raw integer 0-10."""
    return BridgeResult(success=True, output=str(value), exit_code=0)


def _score_fail(error: str = "scorer timed out") -> BridgeResult:
    """A failed scoring bridge result (timeout / non-zero exit)."""
    return BridgeResult(success=False, output="", exit_code=1, error=error)


def _score_unparseable(output: str = "the score is roughly average") -> BridgeResult:
    """A successful scoring call whose output carries no clean integer."""
    return BridgeResult(success=True, output=output, exit_code=0)


def _read_report(root: Path) -> str:
    return (root / "research" / "report.md").read_text()


def test_strong_score_keeps_all_sections(tmp_path: Path):
    """Fixture present + score 10 keeps every section; nothing discarded."""
    _write_fixture(tmp_path, ["How does this advance the vision?"])
    bridge = MagicMock()
    # Two topics: gen -> score(10) each. No retries (strong on first score).
    bridge.run.side_effect = [_gen(), _score(10), _gen(), _score(10)]

    adapter = ResearchAdapter(root=tmp_path, dry_run=False, bridge=bridge)
    result = adapter.execute(InterviewAnswers(research_focus="websockets, gRPC"))

    assert result.success
    report = _read_report(tmp_path)
    assert "- Kept: 2 sections" in report
    assert "- Discarded: none" in report
    assert "kept=2 discarded=0" in result.output


def test_persistently_weak_section_is_discarded(tmp_path: Path):
    """Fixture present + score 0 exhausts the retry budget and discards the topic.

    With a single topic that yields produced==0 -> ToolResult.success is False.
    """
    _write_fixture(tmp_path, ["How does this advance the vision?"])
    bridge = MagicMock()
    # gen -> score(0) -> regenerate -> score(0): budget (1 retry) exhausted, discard.
    bridge.run.side_effect = [_gen(), _score(0), _gen(), _score(0)]

    adapter = ResearchAdapter(root=tmp_path, dry_run=False, bridge=bridge)
    result = adapter.execute(InterviewAnswers(research_focus="websockets"))

    assert not result.success
    assert bridge.run.call_count == 4  # 2 generations + 2 scorings
    report = _read_report(tmp_path)
    assert "- Kept: 0 sections" in report
    assert "- Discarded: websockets" in report


def test_weak_then_strong_keeps_after_one_retry_with_same_prompt(tmp_path: Path):
    """Weak-then-strong across calls keeps the section after one regeneration.

    The regeneration prompt must be byte-identical to the initial topic prompt
    (no prompt mutation, MECH-01), and the scoring call must use allowed_tools=[].
    """
    _write_fixture(tmp_path, ["How does this advance the vision?"])
    bridge = MagicMock()
    # gen1 -> score(0) -> gen2(regenerate) -> score(10): kept after one retry.
    bridge.run.side_effect = [_gen(), _score(0), _gen(), _score(10)]

    adapter = ResearchAdapter(root=tmp_path, dry_run=False, bridge=bridge)
    result = adapter.execute(InterviewAnswers(research_focus="websockets"))

    assert result.success
    calls = bridge.run.call_args_list
    assert len(calls) == 4
    # Call 0 = initial generation, call 2 = regeneration — prompts must match exactly.
    assert calls[2].args[0] == calls[0].args[0]
    # Call 1 = scoring — the judge cannot browse.
    assert calls[1].kwargs["allowed_tools"] == []
    # Generation calls use the web-search tools.
    assert calls[0].kwargs["allowed_tools"] == ["WebSearch", "WebFetch"]
    assert "kept=1 discarded=0" in result.output


def test_no_fixture_skips_scoring_and_keeps_all(tmp_path: Path):
    """No fixture -> scoring skipped, all bridge-successful sections kept."""
    bridge = MagicMock()
    # No scoring calls should be issued — only one generation per topic.
    bridge.run.side_effect = [_gen(), _gen()]

    adapter = ResearchAdapter(root=tmp_path, dry_run=False, bridge=bridge)
    result = adapter.execute(InterviewAnswers(research_focus="websockets, gRPC"))

    assert result.success
    assert bridge.run.call_count == 2  # no scoring calls
    report = _read_report(tmp_path)
    assert "- Kept: 2 sections" in report
    assert "scoring skipped: no fixture" in report


def test_score_groundedness_bridge_failure_returns_none(tmp_path: Path):
    """A failed scoring bridge call returns the None sentinel, NOT 0.0."""
    bridge = MagicMock()
    bridge.run.return_value = _score_fail()
    adapter = ResearchAdapter(root=tmp_path, dry_run=False, bridge=bridge)
    assert adapter._score_groundedness("section", ["q?"]) is None


def test_score_groundedness_unparseable_returns_none(tmp_path: Path):
    """A successful scoring call with no clean integer returns None, NOT 0.0."""
    bridge = MagicMock()
    bridge.run.return_value = _score_unparseable()
    adapter = ResearchAdapter(root=tmp_path, dry_run=False, bridge=bridge)
    assert adapter._score_groundedness("section", ["q?"]) is None


def test_score_groundedness_clean_seven_normalizes(tmp_path: Path):
    """A clean '7' still normalizes to 0.7 (unchanged behavior)."""
    bridge = MagicMock()
    bridge.run.return_value = _score(7)
    adapter = ResearchAdapter(root=tmp_path, dry_run=False, bridge=bridge)
    assert adapter._score_groundedness("section", ["q?"]) == 0.7


def test_scorer_unavailable_keeps_section_fail_open(tmp_path: Path):
    """A down scorer KEEPS the section (fail-open) and reports it distinctly."""
    _write_fixture(tmp_path, ["How does this advance the vision?"])
    bridge = MagicMock()
    # gen -> score fails: section is kept (fail-open), no retry loop.
    bridge.run.side_effect = [_gen(), _score_fail("scorer down")]

    adapter = ResearchAdapter(root=tmp_path, dry_run=False, bridge=bridge)
    result = adapter.execute(InterviewAnswers(research_focus="websockets"))

    assert result.success
    # Only gen + one score call — a None short-circuits the retry loop.
    assert bridge.run.call_count == 2
    report = _read_report(tmp_path)
    assert "- Kept: 1 sections" in report
    assert "Scorer-unavailable (kept): websockets" in report
    # Not counted among discarded-low-score topics.
    assert "- Discarded: none" in report


def test_scorer_unavailable_distinct_from_discarded_in_report(tmp_path: Path):
    """Two topics: one scorer-down (kept), one genuinely low (discarded)."""
    _write_fixture(tmp_path, ["How does this advance the vision?"])
    bridge = MagicMock()
    # topic1: gen -> score fails (kept). topic2: gen -> score(0) -> regen -> score(0) (discarded).
    bridge.run.side_effect = [
        _gen(),
        _score_fail("scorer down"),
        _gen(),
        _score(0),
        _gen(),
        _score(0),
    ]

    adapter = ResearchAdapter(root=tmp_path, dry_run=False, bridge=bridge)
    result = adapter.execute(InterviewAnswers(research_focus="websockets, gRPC"))

    assert result.success  # one section kept
    report = _read_report(tmp_path)
    assert "- Kept: 1 sections" in report
    assert "Scorer-unavailable (kept): websockets" in report
    assert "- Discarded: gRPC" in report


def test_produced_zero_error_distinguishes_scorer_down(tmp_path: Path):
    """When produced==0 and the only failure was a down scorer, the section is kept.

    A single topic whose scorer fails is KEPT (fail-open), so produced==1 and the
    result succeeds — a down scorer can no longer empty the report on its own.
    """
    _write_fixture(tmp_path, ["How does this advance the vision?"])
    bridge = MagicMock()
    bridge.run.side_effect = [_gen(), _score_fail("scorer down")]

    adapter = ResearchAdapter(root=tmp_path, dry_run=False, bridge=bridge)
    result = adapter.execute(InterviewAnswers(research_focus="websockets"))

    assert result.success
    assert "kept=1" in result.output


def test_produced_zero_error_names_scorer_unavailable_when_mixed(tmp_path: Path):
    """produced==0 error text names scorer-unavailable topics distinctly.

    Constructed so the only topic that would keep is bridge-failed and a second is
    genuinely discarded — leaving produced==0 while a scorer-unavailable clause is
    still reachable via a third topic whose scorer is down but generation empty.
    """
    _write_fixture(tmp_path, ["How does this advance the vision?"])
    bridge = MagicMock()
    # topic1 (websockets): generation fails entirely (3 attempts) -> bridge-failed.
    # topic2 (gRPC): gen -> score(0) -> regen -> score(0) -> discarded-low-score.
    fail = BridgeResult(success=False, output="", exit_code=1, error="gen down")
    bridge.run.side_effect = [
        fail,
        fail,
        fail,
        _gen(),
        _score(0),
        _gen(),
        _score(0),
    ]

    adapter = ResearchAdapter(root=tmp_path, dry_run=False, bridge=bridge)
    result = adapter.execute(InterviewAnswers(research_focus="websockets, gRPC"))

    assert not result.success
    assert "bridge-failed: websockets" in result.error
    assert "ungrounded/discarded: gRPC" in result.error


def test_dry_run_report_is_byte_identical_to_mock(tmp_path: Path):
    """Golden: --dry-run output equals MOCK_REPORT.format(...) exactly."""
    from flowstate.bridge import ClaudeBridge

    adapter = ResearchAdapter(root=tmp_path, dry_run=True, bridge=ClaudeBridge(dry_run=True))
    result = adapter.execute(InterviewAnswers(research_focus="websockets, gRPC"))

    assert result.success
    report = _read_report(tmp_path)
    assert report == MOCK_REPORT.format(focus="websockets, gRPC")
