"""Markdown renderer for `flowstate status --markdown`.

Pure function: build a markdown document from FlowStateModel + on-disk memory store.
Used for cross-session handoff (copy-paste / commit / cat from another terminal).
"""

from __future__ import annotations

import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from flowstate import __version__
from flowstate.memory import MemoryKind, MemoryStore
from flowstate.state import FlowStateModel, ToolState, ToolStatus

EM_DASH = "—"
MAX_ARTIFACTS_INLINE = 3


def _fmt_dt(dt: datetime | None) -> str:
    if dt is None:
        return EM_DASH
    return dt.isoformat(timespec="seconds")


def _fmt_duration(ts: ToolState) -> str:
    if ts.started_at and ts.completed_at:
        delta = ts.completed_at - ts.started_at
        total_seconds = int(delta.total_seconds())
        if total_seconds < 60:
            return f"{total_seconds}s"
        minutes, seconds = divmod(total_seconds, 60)
        return f"{minutes}m {seconds}s"
    if ts.status == ToolStatus.RUNNING and ts.started_at:
        return "running"
    return EM_DASH


def _fmt_artifacts(artifacts: list[str]) -> str:
    if not artifacts:
        return EM_DASH
    if len(artifacts) <= MAX_ARTIFACTS_INLINE:
        return ", ".join(artifacts)
    shown = ", ".join(artifacts[:MAX_ARTIFACTS_INLINE])
    extra = len(artifacts) - MAX_ARTIFACTS_INLINE
    return f"{shown} (+{extra} more)"


def _fmt_error(err: str | None) -> str:
    if not err:
        return EM_DASH
    # Markdown table cells can't contain raw pipes or newlines
    return err.replace("|", "\\|").replace("\n", " ")


def _render_tools_table(tools: dict[str, ToolState]) -> str:
    lines = [
        "## Tools",
        "",
        "| Tool | Status | Started | Completed | Duration | Artifacts | Error |",
        "|------|--------|---------|-----------|----------|-----------|-------|",
    ]
    for name, ts in tools.items():
        lines.append(
            f"| {name} | {ts.status.value} | {_fmt_dt(ts.started_at)} | "
            f"{_fmt_dt(ts.completed_at)} | {_fmt_duration(ts)} | "
            f"{_fmt_artifacts(ts.artifacts)} | {_fmt_error(ts.error)} |"
        )
    return "\n".join(lines)


def _render_active_phase(root: Path) -> str:
    roadmap = root / ".planning" / "ROADMAP.md"
    if not roadmap.exists():
        return "## Active Phase\n\nNo active phase (no .planning/ROADMAP.md)."
    text = roadmap.read_text()
    # Look for `- [ ] **Phase N: name**` markers first (in-progress phases)
    unchecked = re.search(r"- \[ \] \*\*(Phase \d+:[^*]+)\*\*", text)
    if unchecked:
        return (
            f"## Active Phase\n\n**{unchecked.group(1).strip()}** (from .planning/ROADMAP.md)"
        )
    # Fall back to first `### Phase N:` heading
    any_phase = re.search(r"###\s+(Phase \d+:[^\n]+)", text)
    if any_phase:
        return f"## Active Phase\n\n**{any_phase.group(1).strip()}** (from .planning/ROADMAP.md)"
    return "## Active Phase\n\nROADMAP.md present but no recognizable phase entries."


def _render_memory_section(root: Path) -> str:
    db_path = root / "memory.db"
    if not db_path.exists():
        return "## Memory\n\nmemory.db not initialized."

    lines = ["## Memory", "", "| Kind | Count |", "|------|-------|"]
    total = 0
    last_entry_iso = EM_DASH
    try:
        with MemoryStore(root=root) as store:
            for kind in MemoryKind:
                count = store.count(kind)
                total += count
                lines.append(f"| {kind.value} | {count} |")
            # Use the public helper instead of poking store._conn
            last_dt = store.last_entry_at()
            if last_dt is not None:
                last_entry_iso = last_dt.isoformat(timespec="seconds")
    except sqlite3.Error as e:
        return f"## Memory\n\nmemory.db error: {e}"

    db_size_mb = db_path.stat().st_size / (1024 * 1024)
    lines.append("")
    lines.append(
        f"**Total entries:** {total} · "
        f"**DB size:** {db_size_mb:.2f} MB · "
        f"**Last entry:** {last_entry_iso}"
    )
    return "\n".join(lines)


def render_status_markdown(state: FlowStateModel, root: Path) -> str:
    """Build the full markdown status document.

    Pure function — never raises on missing files. Reads state.tools,
    state.preferences.project_name, and state.install_manifest (indirectly via root).
    """
    project_label = state.preferences.project_name or root.name
    lines = [
        f"# FlowState Status — {project_label}",
        "",
        f"**Generated:** {datetime.now(UTC).isoformat(timespec='seconds')}",
        f"**Version:** {__version__}",
        f"**Root:** `{root.resolve()}`",
        "",
        _render_tools_table(state.tools),
        "",
        _render_active_phase(root),
        "",
        _render_memory_section(root),
        "",
    ]
    return "\n".join(lines)
