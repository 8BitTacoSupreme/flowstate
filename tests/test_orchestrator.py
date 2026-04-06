"""Tests for FlowState orchestrator — dry-run pipeline."""

from pathlib import Path

from flowstate.orchestrator import run_pipeline
from flowstate.state import FlowStateModel, ToolStatus


def test_dry_run_pipeline(tmp_path: Path):
    state = FlowStateModel()
    state.preferences.dry_run = True
    state.preferences.project_name = "test-proj"
    state.interview.research_focus = "REST API design"
    state.interview.core_problem = "Developer onboarding is slow"
    state.interview.ten_x_vision = "Zero-config project setup"
    state.interview.milestones = ["Intake", "Pipeline", "Polish"]
    state.interview.test_coverage = 85
    state.interview.architecture_pattern = "hexagonal"

    result = run_pipeline(state, tmp_path)

    # All tools should complete in dry-run
    for name, ts in result.tools.items():
        assert ts.status == ToolStatus.COMPLETED, f"{name} not completed: {ts.status}"

    # Artifacts should be created
    assert (tmp_path / "research" / "report.md").exists()
    assert (tmp_path / "research" / "strategy.md").exists()
    assert (tmp_path / ".planning" / "ROADMAP.md").exists()


def test_dry_run_creates_state_file(tmp_path: Path):
    state = FlowStateModel()
    state.preferences.dry_run = True
    run_pipeline(state, tmp_path)

    assert (tmp_path / "flowstate.json").exists()


def test_dry_run_creates_context_files(tmp_path: Path):
    state = FlowStateModel()
    state.preferences.dry_run = True
    state.interview.research_focus = "testing"
    state.interview.core_problem = "slow tests"
    state.preferences.project_name = "ctx-test"

    run_pipeline(state, tmp_path)

    # Context generation should create these files
    assert (tmp_path / ".planning" / "PROJECT.md").exists()
    assert (tmp_path / ".claude" / "CLAUDE.md").exists()
    assert (tmp_path / "research" / "brief.md").exists()
