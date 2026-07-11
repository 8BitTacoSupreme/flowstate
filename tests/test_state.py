"""Tests for FlowState state manager."""

import json
from pathlib import Path

from flowstate.state import (
    FlowStateModel,
    ToolStatus,
    _migrate_state,
    load_state,
    save_state,
    update_tool,
)


def test_default_state():
    state = FlowStateModel()
    assert len(state.tools) == 4
    assert "research" in state.tools
    assert "strategy" in state.tools
    assert "gsd" in state.tools
    assert "discipline" in state.tools
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
    update_tool(state, "research", status=ToolStatus.RUNNING)
    assert state.tools["research"].status == ToolStatus.RUNNING
    assert state.tools["research"].started_at is not None

    update_tool(state, "research", status=ToolStatus.COMPLETED, artifact="research/report.md")
    assert state.tools["research"].status == ToolStatus.COMPLETED
    assert "research/report.md" in state.tools["research"].artifacts


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


def test_context_files_field():
    state = FlowStateModel()
    assert state.context_files == []
    state.context_files = [".planning/PROJECT.md", ".planning/ROADMAP.md"]
    assert len(state.context_files) == 2


def test_migrate_v010_state():
    """Old v0.1.0 state with autoresearch/gstack/superpowers keys gets chain-migrated to v0.4.0."""
    old_data = {
        "version": "0.1.0",
        "tools": {
            "autoresearch": {"status": "completed", "artifacts": ["report.md"]},
            "gstack": {"status": "completed", "artifacts": ["strategy.md"]},
            "gsd": {"status": "ready"},
            "superpowers": {"status": "blocked", "error": "timeout"},
        },
    }
    migrated = _migrate_state(old_data)
    # Chained migration: v0.1.0 → v0.2.0 → v0.3.0 → v0.4.0
    assert migrated["version"] == "0.4.0"
    assert "research" in migrated["tools"]
    assert "strategy" in migrated["tools"]
    assert "discipline" in migrated["tools"]
    assert "autoresearch" not in migrated["tools"]
    assert "gstack" not in migrated["tools"]
    assert "superpowers" not in migrated["tools"]
    # v0.2.0 → v0.3.0 added install_manifest
    assert migrated["install_manifest"] == []


def test_chained_migration_v010_to_v040():
    """Explicit test of the full chained migration path."""
    old_data = {
        "version": "0.1.0",
        "tools": {
            "autoresearch": {"status": "ready"},
            "gstack": {"status": "ready"},
            "gsd": {"status": "ready"},
            "superpowers": {"status": "ready"},
        },
    }
    migrated = _migrate_state(old_data)
    assert migrated["version"] == "0.4.0"
    assert "install_manifest" in migrated
    assert "context_files" in migrated  # added by v0.2.0 step


def test_migrate_v030_to_v040():
    """v0.3.0 state migrates to v0.4.0 (guard no longer short-circuits at 0.3.0)."""
    data = {
        "version": "0.3.0",
        "tools": {
            "research": {"status": "ready"},
            "strategy": {"status": "ready"},
            "gsd": {"status": "ready"},
            "discipline": {"status": "ready"},
        },
        "install_manifest": [],
    }
    migrated = _migrate_state(data)
    assert migrated["version"] == "0.4.0"
    assert "research" in migrated["tools"]


def test_preferences_model_fields():
    """New model/budget/effort fields have correct defaults."""
    state = FlowStateModel()
    assert state.preferences.model == ""
    assert state.preferences.max_budget_usd is None
    assert state.preferences.effort == ""


def test_preferences_enable_prompt_caching_1h_default():
    """enable_prompt_caching_1h defaults to True."""
    prefs = FlowStateModel().preferences
    assert prefs.enable_prompt_caching_1h is True


def test_preferences_wiki_layer_default_false():
    """wiki_layer defaults to False (opt-in; byte-identical default path — D-05)."""
    from flowstate.state import ProjectPreferences

    assert ProjectPreferences().wiki_layer is False
    assert FlowStateModel().preferences.wiki_layer is False


def test_preferences_wiki_layer_roundtrip_true(tmp_path: Path):
    """wiki_layer=True survives save/load."""
    state = FlowStateModel()
    state.preferences.wiki_layer = True
    save_state(state, tmp_path)

    loaded = load_state(tmp_path)
    assert loaded.preferences.wiki_layer is True


def test_preferences_model_roundtrip(tmp_path: Path):
    """Model preferences survive save/load."""
    state = FlowStateModel()
    state.preferences.model = "haiku"
    state.preferences.max_budget_usd = 0.50
    state.preferences.effort = "low"
    save_state(state, tmp_path)

    loaded = load_state(tmp_path)
    assert loaded.preferences.model == "haiku"
    assert loaded.preferences.max_budget_usd == 0.50
    assert loaded.preferences.effort == "low"


def test_preferences_prompt_caching_roundtrip_false(tmp_path: Path):
    """enable_prompt_caching_1h=False survives save/load."""
    state = FlowStateModel()
    state.preferences.enable_prompt_caching_1h = False
    save_state(state, tmp_path)

    loaded = load_state(tmp_path)
    assert loaded.preferences.enable_prompt_caching_1h is False


def test_load_state_without_caching_field_defaults_true(tmp_path: Path):
    """Existing flowstate.json without enable_prompt_caching_1h loads with default True."""
    raw = {
        "version": "0.4.0",
        "preferences": {
            "project_name": "legacy-proj",
            "dry_run": False,
            "auto_branch_on_hardening": True,
            "model": "",
            "max_budget_usd": None,
            "effort": "",
            # enable_prompt_caching_1h intentionally absent
        },
        "tools": {
            "research": {"status": "ready"},
            "strategy": {"status": "ready"},
            "gsd": {"status": "ready"},
            "discipline": {"status": "ready"},
        },
        "install_manifest": [],
    }
    import json as _json

    (tmp_path / "flowstate.json").write_text(_json.dumps(raw))
    loaded = load_state(tmp_path)
    assert loaded.preferences.enable_prompt_caching_1h is True


def test_load_v010_state_file(tmp_path: Path):
    """Loading a v0.1.0 state file should migrate it transparently."""
    old_state = {
        "version": "0.1.0",
        "created_at": "2025-01-01T00:00:00Z",
        "updated_at": "2025-01-01T00:00:00Z",
        "interview": {
            "research_focus": "test",
            "core_problem": "",
            "ten_x_vision": "",
            "milestones": [],
            "test_coverage": 80,
            "architecture_pattern": "",
        },
        "preferences": {
            "project_name": "old-proj",
            "dry_run": False,
            "auto_branch_on_hardening": True,
        },
        "tools": {
            "autoresearch": {"status": "completed", "artifacts": ["report.md"]},
            "gstack": {"status": "ready"},
            "gsd": {"status": "ready"},
            "superpowers": {"status": "ready"},
        },
        "artifacts": {},
    }
    (tmp_path / "flowstate.json").write_text(json.dumps(old_state))
    loaded = load_state(tmp_path)
    assert "research" in loaded.tools
    assert loaded.tools["research"].status == ToolStatus.COMPLETED
    # Chained migration brings v0.1.0 up to current v0.4.0
    assert loaded.version == "0.4.0"
