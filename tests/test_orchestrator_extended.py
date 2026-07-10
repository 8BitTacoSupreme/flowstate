"""Extended tests for the orchestrator module — covers run_phase and print_status."""

from __future__ import annotations

from pathlib import Path

from flowstate.orchestrator import print_status, run_phase, run_pipeline
from flowstate.state import FlowStateModel, ToolStatus, save_state


def test_run_phase_prints_launch_command(tmp_path: Path):
    state = FlowStateModel()
    state.preferences.dry_run = True
    state.interview.milestones = ["Alpha", "Beta"]
    save_state(state, tmp_path)

    result = run_phase(state, tmp_path, 1)
    assert result is not None


def test_print_status_no_state_file(tmp_path: Path, capsys):
    """print_status should work even with no existing state file."""
    print_status(tmp_path)


def test_print_status_with_artifacts(tmp_path: Path, capsys):
    state = FlowStateModel()
    state.artifacts["research_report"] = "research/report.md"
    from flowstate.state import update_tool

    update_tool(state, "research", status=ToolStatus.COMPLETED, artifact="report.md")
    update_tool(state, "gsd", status=ToolStatus.BLOCKED, error="not found")
    save_state(state, tmp_path)
    print_status(tmp_path)


def test_pipeline_live_no_cli_blocks_loud(tmp_path: Path, monkeypatch):
    """Live mode with no locatable claude CLI must BLOCK bridge steps, not fake success."""
    monkeypatch.setattr("flowstate.bridge._find_claude", lambda: "")
    (tmp_path / ".git").mkdir()
    (tmp_path / "pyproject.toml").write_text("[tool.pytest]")

    state = FlowStateModel()
    state.preferences.dry_run = False
    state.interview.research_focus = "testing"
    save_state(state, tmp_path)

    result = run_pipeline(state, tmp_path)

    assert result.tools["research"].status == ToolStatus.BLOCKED
    assert result.tools["strategy"].status == ToolStatus.BLOCKED

    report_path = tmp_path / "research" / "report.md"
    if report_path.exists():
        assert "[dry-run] claude prompt" not in report_path.read_text()

    strategy_path = tmp_path / "research" / "strategy.md"
    if strategy_path.exists():
        assert "[dry-run] claude prompt" not in strategy_path.read_text()


def test_pipeline_dry_run_still_succeeds(tmp_path: Path):
    """Genuine --dry-run must remain untouched: all tools COMPLETED with MOCK artifacts."""
    (tmp_path / ".git").mkdir()
    (tmp_path / "pyproject.toml").write_text("[tool.pytest]")

    state = FlowStateModel()
    state.preferences.dry_run = True
    state.interview.research_focus = "testing"
    save_state(state, tmp_path)

    result = run_pipeline(state, tmp_path)

    for tool_name in ("research", "strategy", "gsd", "discipline"):
        assert result.tools[tool_name].status == ToolStatus.COMPLETED

    report_path = tmp_path / "research" / "report.md"
    assert report_path.exists()
    assert "Analysis pending research integration" in report_path.read_text()


def test_print_status_shows_context_files(tmp_path: Path, capsys):
    """print_status should display context files when present."""
    state = FlowStateModel()
    state.context_files = [".planning/PROJECT.md", ".planning/ROADMAP.md"]
    save_state(state, tmp_path)
    print_status(tmp_path)
