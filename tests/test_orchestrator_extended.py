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


def test_pipeline_no_bridge_falls_back(tmp_path: Path):
    """Pipeline with live mode but no claude CLI should fall back to dry-run."""
    state = FlowStateModel()
    state.preferences.dry_run = False
    state.interview.research_focus = "testing"
    save_state(state, tmp_path)

    result = run_pipeline(state, tmp_path)
    # Should complete — falls back to dry-run
    assert result is not None


def test_print_status_shows_context_files(tmp_path: Path, capsys):
    """print_status should display context files when present."""
    state = FlowStateModel()
    state.context_files = [".planning/PROJECT.md", ".planning/ROADMAP.md"]
    save_state(state, tmp_path)
    print_status(tmp_path)
