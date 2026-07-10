"""Offline tests for the strategy adapter's scored rubric (MECH-02).

Covers `_parse_rubric` directly (valid + each invalid case) and drives
`pressure_test` with a MagicMock bridge for the success and unparseable-failure
integration paths. No test requires a live `claude` CLI or network.
"""

from pathlib import Path
from unittest.mock import MagicMock

from flowstate.bridge import BridgeResult, ClaudeBridge
from flowstate.state import InterviewAnswers
from flowstate.tools.strategy import (
    MOCK_STRATEGY,
    StrategyAdapter,
    _parse_rubric,
)

_VALID_RUBRIC = """\
# Strategy: Pressure Test

Prose assessment goes here.

```rubric
problem_clarity: 8
ten_x_potential: 7
feasibility: 6
risk: 4
recommendation: 9
verdict: ship
```
"""


def test_parse_rubric_valid():
    parsed = _parse_rubric(_VALID_RUBRIC)
    assert parsed is not None
    scores, verdict = parsed
    assert scores == {
        "problem_clarity": 8,
        "ten_x_potential": 7,
        "feasibility": 6,
        "risk": 4,
        "recommendation": 9,
    }
    assert verdict == "ship"
    assert all(0 <= v <= 10 for v in scores.values())


def test_parse_rubric_verdict_case_insensitive():
    text = _VALID_RUBRIC.replace("verdict: ship", "verdict: PIVOT")
    parsed = _parse_rubric(text)
    assert parsed is not None
    _, verdict = parsed
    assert verdict == "pivot"


def test_parse_rubric_missing_dimension():
    text = _VALID_RUBRIC.replace("feasibility: 6\n", "")
    assert _parse_rubric(text) is None


def test_parse_rubric_out_of_range_score():
    text = _VALID_RUBRIC.replace("problem_clarity: 8", "problem_clarity: 42")
    assert _parse_rubric(text) is None


def test_parse_rubric_invalid_verdict():
    text = _VALID_RUBRIC.replace("verdict: ship", "verdict: maybe")
    assert _parse_rubric(text) is None


def test_parse_rubric_no_rubric_block():
    assert _parse_rubric("# Strategy\n\nJust prose, no rubric here.\n") is None


def test_pressure_test_valid_rubric_writes_and_succeeds(tmp_path: Path):
    bridge = MagicMock()
    bridge.run.return_value = BridgeResult(success=True, output=_VALID_RUBRIC, exit_code=0)

    adapter = StrategyAdapter(root=tmp_path, dry_run=False, bridge=bridge)
    answers = InterviewAnswers(core_problem="Slow deploys", ten_x_vision="One-click shipping")
    result = adapter.pressure_test(answers)

    strategy_path = tmp_path / "research" / "strategy.md"
    assert result.success
    assert strategy_path.exists()
    assert "ship" in result.output
    content = strategy_path.read_text()
    assert "## Rubric" in content
    assert "**Verdict:** ship" in content


def test_pressure_test_unparseable_rubric_fails_and_writes_nothing(tmp_path: Path):
    bridge = MagicMock()
    bridge.run.return_value = BridgeResult(
        success=True, output="# Strategy\n\nProse only, no rubric.\n", exit_code=0
    )

    adapter = StrategyAdapter(root=tmp_path, dry_run=False, bridge=bridge)
    answers = InterviewAnswers(core_problem="Slow deploys", ten_x_vision="Fast")
    result = adapter.pressure_test(answers)

    assert not result.success
    assert "unparseable rubric" in (result.error or "")
    assert result.artifacts == []
    assert not (tmp_path / "research" / "strategy.md").exists()


def test_pressure_test_dry_run_golden(tmp_path: Path):
    adapter = StrategyAdapter(root=tmp_path, dry_run=True, bridge=ClaudeBridge(dry_run=True))
    answers = InterviewAnswers(core_problem="Slow deploys", ten_x_vision="One-click shipping")
    result = adapter.pressure_test(answers)

    assert result.success
    expected = MOCK_STRATEGY.format(
        problem="Slow deploys",
        vision="One-click shipping",
    )
    assert (tmp_path / "research" / "strategy.md").read_text() == expected
