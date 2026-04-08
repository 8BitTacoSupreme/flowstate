"""Tests for tool adapters."""

from pathlib import Path

from flowstate.bridge import ClaudeBridge
from flowstate.state import FlowStateModel, InterviewAnswers
from flowstate.tools.gsd_adapter import GSDAdapter
from flowstate.tools.research import ResearchAdapter
from flowstate.tools.strategy import StrategyAdapter


def _mock_bridge() -> ClaudeBridge:
    return ClaudeBridge(dry_run=True)


def test_research_dry_run(tmp_path: Path):
    adapter = ResearchAdapter(root=tmp_path, dry_run=True, bridge=_mock_bridge())
    answers = InterviewAnswers(research_focus="websocket libraries")
    result = adapter.execute(answers)

    assert result.success
    assert (tmp_path / "research" / "report.md").exists()
    content = (tmp_path / "research" / "report.md").read_text()
    assert "websocket libraries" in content


def test_research_multi_topic_dry_run(tmp_path: Path):
    adapter = ResearchAdapter(root=tmp_path, dry_run=True, bridge=_mock_bridge())
    answers = InterviewAnswers(research_focus="websockets, gRPC, REST APIs")
    result = adapter.execute(answers)

    assert result.success
    content = (tmp_path / "research" / "report.md").read_text()
    assert "websockets" in content
    assert "gRPC" in content
    assert "REST APIs" in content


def test_strategy_dry_run(tmp_path: Path):
    adapter = StrategyAdapter(root=tmp_path, dry_run=True, bridge=_mock_bridge())
    answers = InterviewAnswers(core_problem="Slow deploys", ten_x_vision="One-click shipping")

    result = adapter.pressure_test(answers)
    assert result.success
    assert (tmp_path / "research" / "strategy.md").exists()


def test_gsd_dry_run(tmp_path: Path):
    adapter = GSDAdapter(root=tmp_path, dry_run=True, bridge=_mock_bridge())
    state = FlowStateModel()
    state.interview.milestones = ["Alpha", "Beta", "GA"]
    result = adapter.new_project(state)

    assert result.success
    content = (tmp_path / ".planning" / "ROADMAP.md").read_text()
    assert "Alpha" in content
    assert "Beta" in content


def test_gsd_live_writes_context_files(tmp_path: Path):
    adapter = GSDAdapter(root=tmp_path, dry_run=False, bridge=_mock_bridge())
    state = FlowStateModel()
    state.interview.milestones = ["Alpha", "Beta"]
    state.interview.core_problem = "Test problem"
    state.preferences.project_name = "test-proj"
    result = adapter.new_project(state)

    assert result.success
    assert (tmp_path / ".planning" / "PROJECT.md").exists()
    assert (tmp_path / ".planning" / "ROADMAP.md").exists()
    assert (tmp_path / ".claude" / "CLAUDE.md").exists()
    assert (tmp_path / "research" / "brief.md").exists()


def test_research_passes_model_to_bridge(tmp_path: Path, monkeypatch):
    """Research adapter passes model='sonnet' to bridge.run()."""
    from unittest.mock import MagicMock

    from flowstate.bridge import BridgeResult

    bridge = MagicMock()
    bridge.run.return_value = BridgeResult(success=True, output="# Research", exit_code=0)

    adapter = ResearchAdapter(root=tmp_path, dry_run=False, bridge=bridge)
    answers = InterviewAnswers(research_focus="websockets")
    adapter.execute(answers)

    call_kwargs = bridge.run.call_args[1]
    assert call_kwargs["model"] == "sonnet"


def test_strategy_passes_model_to_bridge(tmp_path: Path):
    """Strategy adapter passes model='sonnet' to bridge.run()."""
    from unittest.mock import MagicMock

    from flowstate.bridge import BridgeResult

    bridge = MagicMock()
    bridge.run.return_value = BridgeResult(success=True, output="# Strategy", exit_code=0)

    adapter = StrategyAdapter(root=tmp_path, dry_run=False, bridge=bridge)
    answers = InterviewAnswers(core_problem="Slow deploys", ten_x_vision="Fast")
    adapter.pressure_test(answers)

    call_kwargs = bridge.run.call_args[1]
    assert call_kwargs["model"] == "sonnet"
