"""FlowState state manager — Pydantic models and persistence for flowstate.json."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field


class ToolStatus(StrEnum):
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    BLOCKED = "blocked"


class ToolState(BaseModel):
    status: ToolStatus = ToolStatus.READY
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None
    artifacts: list[str] = Field(default_factory=list)


class InterviewAnswers(BaseModel):
    research_focus: str = ""
    core_problem: str = ""
    ten_x_vision: str = ""
    milestones: list[str] = Field(default_factory=list)
    test_coverage: int = 80
    architecture_pattern: str = ""


class ProjectPreferences(BaseModel):
    project_name: str = ""
    dry_run: bool = False
    auto_branch_on_hardening: bool = True
    model: str = ""
    max_budget_usd: float | None = None
    effort: str = ""


# Old tool keys for migration
_OLD_TOOL_KEYS = {
    "autoresearch": "research",
    "gstack": "strategy",
    "superpowers": "discipline",
}
_CURRENT_TOOL_KEYS = ["research", "strategy", "gsd", "discipline"]


class FlowStateModel(BaseModel):
    version: str = "0.2.0"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    interview: InterviewAnswers = Field(default_factory=InterviewAnswers)
    preferences: ProjectPreferences = Field(default_factory=ProjectPreferences)
    tools: dict[str, ToolState] = Field(
        default_factory=lambda: {
            "research": ToolState(),
            "strategy": ToolState(),
            "gsd": ToolState(),
            "discipline": ToolState(),
        }
    )
    artifacts: dict[str, str] = Field(default_factory=dict)
    context_files: list[str] = Field(default_factory=list)


STATE_FILE = "flowstate.json"


def state_path(root: Path | None = None) -> Path:
    return (root or Path.cwd()) / STATE_FILE


def _migrate_state(data: dict) -> dict:
    """Migrate v0.1.0 state (old tool keys) to v0.2.0."""
    version = data.get("version", "0.1.0")
    if version >= "0.2.0":
        return data

    tools = data.get("tools", {})
    migrated_tools = {}
    for old_key, new_key in _OLD_TOOL_KEYS.items():
        if old_key in tools:
            migrated_tools[new_key] = tools[old_key]
    # Keep gsd as-is
    if "gsd" in tools:
        migrated_tools["gsd"] = tools["gsd"]
    # Fill any missing keys
    for key in _CURRENT_TOOL_KEYS:
        if key not in migrated_tools:
            migrated_tools[key] = ToolState().model_dump()

    data["tools"] = migrated_tools
    data["version"] = "0.2.0"
    if "context_files" not in data:
        data["context_files"] = []

    return data


def load_state(root: Path | None = None) -> FlowStateModel:
    p = state_path(root)
    if p.exists():
        import json as json_mod

        raw = json_mod.loads(p.read_text())
        migrated = _migrate_state(raw)
        return FlowStateModel.model_validate(migrated)
    return FlowStateModel()


def save_state(state: FlowStateModel, root: Path | None = None) -> Path:
    p = state_path(root)
    state.updated_at = datetime.now(UTC)
    p.write_text(state.model_dump_json(indent=2) + "\n")
    return p


def update_tool(
    state: FlowStateModel,
    tool: str,
    *,
    status: ToolStatus | None = None,
    error: str | None = None,
    artifact: str | None = None,
) -> None:
    ts = state.tools[tool]
    if status is not None:
        ts.status = status
        if status == ToolStatus.RUNNING:
            ts.started_at = datetime.now(UTC)
        elif status in (ToolStatus.COMPLETED, ToolStatus.BLOCKED):
            ts.completed_at = datetime.now(UTC)
    if error is not None:
        ts.error = error
    if artifact is not None:
        ts.artifacts.append(artifact)
