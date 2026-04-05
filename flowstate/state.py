"""FlowState state manager — Pydantic models and persistence for flowstate.json."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class ToolStatus(str, Enum):
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


class FlowStateModel(BaseModel):
    version: str = "0.1.0"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    interview: InterviewAnswers = Field(default_factory=InterviewAnswers)
    preferences: ProjectPreferences = Field(default_factory=ProjectPreferences)
    tools: dict[str, ToolState] = Field(default_factory=lambda: {
        "autoresearch": ToolState(),
        "gstack": ToolState(),
        "gsd": ToolState(),
        "superpowers": ToolState(),
    })
    artifacts: dict[str, str] = Field(default_factory=dict)


STATE_FILE = "flowstate.json"


def state_path(root: Path | None = None) -> Path:
    return (root or Path.cwd()) / STATE_FILE


def load_state(root: Path | None = None) -> FlowStateModel:
    p = state_path(root)
    if p.exists():
        return FlowStateModel.model_validate_json(p.read_text())
    return FlowStateModel()


def save_state(state: FlowStateModel, root: Path | None = None) -> Path:
    p = state_path(root)
    state.updated_at = datetime.now(timezone.utc)
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
            ts.started_at = datetime.now(timezone.utc)
        elif status in (ToolStatus.COMPLETED, ToolStatus.BLOCKED):
            ts.completed_at = datetime.now(timezone.utc)
    if error is not None:
        ts.error = error
    if artifact is not None:
        ts.artifacts.append(artifact)
