"""FlowState state manager — Pydantic models and persistence for flowstate.json."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Literal

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


class InstallEntry(BaseModel):
    """A single file FlowState owns — recorded at write time, consulted by `fresh`."""

    path: str
    owner: str
    kind: Literal["config", "context", "memory", "research", "artifact"]
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    checksum: str | None = None


# Old tool keys for migration
_OLD_TOOL_KEYS = {
    "autoresearch": "research",
    "gstack": "strategy",
    "superpowers": "discipline",
}
_CURRENT_TOOL_KEYS = ["research", "strategy", "gsd", "discipline"]


class FlowStateModel(BaseModel):
    version: str = "0.3.0"
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
    install_manifest: list[InstallEntry] = Field(default_factory=list)


STATE_FILE = "flowstate.json"


def state_path(root: Path | None = None) -> Path:
    return (root or Path.cwd()) / STATE_FILE


def _migrate_state(data: dict) -> dict:
    """Migrate older state JSON forward.

    v0.1.0 → v0.2.0: rename old tool keys (autoresearch/gstack/superpowers).
    v0.2.0 → v0.3.0: add empty install_manifest (filled in by backfill on first load).
    """
    version = data.get("version", "0.1.0")
    if version >= "0.3.0":
        return data

    # v0.1.0 → v0.2.0 (tool key rename)
    if version < "0.2.0":
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
        version = "0.2.0"

    # v0.2.0 → v0.3.0 (install_manifest field)
    if version < "0.3.0":
        if "install_manifest" not in data:
            data["install_manifest"] = []
        data["version"] = "0.3.0"

    return data


def _backfill_manifest(root: Path) -> list[dict]:
    """Synthesize InstallEntry dicts for files already on disk.

    Used when migrating a pre-manifest flowstate.json. Best-effort owner detection:
    .planning/* → context, research/* → research_adapter, memory.db → memory.
    Never raises on missing files.
    """
    now = datetime.now(UTC).isoformat()
    entries: list[dict] = []

    planning = root / ".planning"
    if planning.is_dir():
        for name in ("PROJECT.md", "ROADMAP.md", "config.json", "CLAUDE.md"):
            p = planning / name
            if p.exists():
                kind = "config" if name.endswith(".json") else "context"
                entries.append(
                    {
                        "path": str(p.relative_to(root)),
                        "owner": "context",
                        "kind": kind,
                        "created_at": now,
                        "checksum": None,
                    }
                )

    claude_dir = root / ".claude"
    if claude_dir.is_dir():
        claude_md = claude_dir / "CLAUDE.md"
        if claude_md.exists():
            entries.append(
                {
                    "path": str(claude_md.relative_to(root)),
                    "owner": "context",
                    "kind": "context",
                    "created_at": now,
                    "checksum": None,
                }
            )

    research = root / "research"
    if research.is_dir():
        for name in ("brief.md", "report.md", "strategy.md"):
            p = research / name
            if p.exists():
                entries.append(
                    {
                        "path": str(p.relative_to(root)),
                        "owner": "research_adapter",
                        "kind": "research",
                        "created_at": now,
                        "checksum": None,
                    }
                )

    memory_db = root / "memory.db"
    if memory_db.exists():
        entries.append(
            {
                "path": "memory.db",
                "owner": "memory",
                "kind": "memory",
                "created_at": now,
                "checksum": None,
            }
        )

    return entries


def load_state(root: Path | None = None) -> FlowStateModel:
    p = state_path(root)
    if p.exists():
        import json as json_mod

        raw = json_mod.loads(p.read_text())
        needed_migration = raw.get("version", "0.1.0") < "0.3.0"
        migrated = _migrate_state(raw)
        # Backfill manifest from disk on first migration to v0.3.0
        if needed_migration and root is not None and not migrated.get("install_manifest"):
            backfilled = _backfill_manifest(root)
            if backfilled:
                migrated["install_manifest"] = backfilled
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
