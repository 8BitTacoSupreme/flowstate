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


def test_dry_run_report_is_byte_identical_to_mock(tmp_path: Path):
    """Golden: --dry-run output equals MOCK_REPORT.format(...) exactly."""
    from flowstate.bridge import ClaudeBridge

    adapter = ResearchAdapter(root=tmp_path, dry_run=True, bridge=ClaudeBridge(dry_run=True))
    result = adapter.execute(InterviewAnswers(research_focus="websockets, gRPC"))

    assert result.success
    report = _read_report(tmp_path)
    assert report == MOCK_REPORT.format(focus="websockets, gRPC")
