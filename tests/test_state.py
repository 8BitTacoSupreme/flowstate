"""Tests for FlowState state manager."""

import json
from pathlib import Path

from flowstate.state import (
    FlowStateModel,
    ToolStatus,
    load_state,
    save_state,
    update_tool,
)


def test_default_state():
    state = FlowStateModel()
    assert len(state.tools) == 4
    for ts in state.tools.values():
        assert ts.status == ToolStatus.READY


def test_save_and_load(tmp_path: Path):
    state = FlowStateModel()
    state.preferences.project_name = "test-project"
    state.interview.research_focus = "websockets"

    save_state(state, tmp_path)
    loaded = load_state(tmp_path)

    assert loaded.preferences.project_name == "test-project"
    assert loaded.interview.research_focus == "websockets"


def test_update_tool_status():
    state = FlowStateModel()
    update_tool(state, "autoresearch", status=ToolStatus.RUNNING)
    assert state.tools["autoresearch"].status == ToolStatus.RUNNING
    assert state.tools["autoresearch"].started_at is not None

    update_tool(state, "autoresearch", status=ToolStatus.COMPLETED, artifact="research/report.md")
    assert state.tools["autoresearch"].status == ToolStatus.COMPLETED
    assert "research/report.md" in state.tools["autoresearch"].artifacts


def test_update_tool_error():
    state = FlowStateModel()
    update_tool(state, "gsd", status=ToolStatus.BLOCKED, error="Command not found")
    assert state.tools["gsd"].status == ToolStatus.BLOCKED
    assert state.tools["gsd"].error == "Command not found"


def test_state_json_roundtrip(tmp_path: Path):
    state = FlowStateModel()
    state.interview.milestones = ["Alpha", "Beta", "GA"]
    state.interview.test_coverage = 90
    save_state(state, tmp_path)

    raw = json.loads((tmp_path / "flowstate.json").read_text())
    assert raw["interview"]["milestones"] == ["Alpha", "Beta", "GA"]
    assert raw["interview"]["test_coverage"] == 90
