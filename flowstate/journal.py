"""Run-journal writer — pure-Python, no bridge/LLM dependency.

Writes exactly one MemoryKind.RUN entry per run_id (idempotent) and mirrors
the entry to .planning/RUNLOG.md as an append-only human-readable trail.
Never raises into the pipeline — all write failures are swallowed.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from flowstate.memory import MemoryEntry, MemoryKind, MemoryStore
from flowstate.state import FlowStateModel


def append_run_entry(
    memory: MemoryStore,
    state: FlowStateModel,
    run_id: str,
    *,
    root: Path,
    dry_run: bool = False,
    timestamp: datetime | None = None,
) -> None:
    """Write one MemoryKind.RUN entry for this run_id (idempotent).

    Fetches the prior RUN entry first to compute the delta. Mirrors to
    .planning/RUNLOG.md as an append-only human-readable trail.
    Never raises — journal failures must not break the pipeline.
    """
    ts = timestamp or datetime.now(UTC)

    # 1. Idempotency guard — fetch existing RUN entries and bail if already journaled
    existing = memory.get_by_kind(MemoryKind.RUN, limit=50)
    if any(e.run_id == run_id for e in existing):
        return

    # 2. Fetch prior RUN entry (newest-first list; existing[0] is most recent)
    prior_entry: MemoryEntry | None = existing[0] if existing else None
    prior_snapshot: dict[str, str] = {}
    if prior_entry is not None:
        prior_snapshot = prior_entry.metadata.get("snapshot", {})

    # 3. Build current checksum snapshot — exclude memory.db (checksum=None)
    current_snapshot: dict[str, str] = {
        entry.path: entry.checksum for entry in state.install_manifest if entry.checksum is not None
    }

    # 4. Diff vs prior snapshot to produce artifacts-changed and delta line
    artifacts_changed: list[str] = []
    if prior_snapshot:
        for path, checksum in current_snapshot.items():
            if prior_snapshot.get(path) != checksum:
                artifacts_changed.append(path)
        for path in prior_snapshot:
            if path not in current_snapshot:
                artifacts_changed.append(path)
        delta_line = _build_delta_line(artifacts_changed, state)
    else:
        delta_line = "first run"

    # 5. Build per-step status map
    tool_names = ("research", "strategy", "gsd", "discipline")
    steps: dict[str, str] = {}
    for name in tool_names:
        ts_entry = state.tools.get(name)
        if ts_entry is not None:
            steps[name] = ts_entry.status.value

    # 6. Build metadata dict
    metadata: dict[str, Any] = {
        "run_id": run_id,
        "snapshot": current_snapshot,
        "steps": steps,
        "artifacts_changed": artifacts_changed,
        "decisions": [],
        "gotchas": [],
        "delta_line": delta_line,
        "dry_run": dry_run,
    }

    # 7. Build human-readable summary and content
    steps_summary = ", ".join(f"{k}:{v}" for k, v in steps.items()) or "none"
    artifacts_summary = ", ".join(artifacts_changed) if artifacts_changed else "none"
    summary = f"run {run_id} — {delta_line}"
    content = (
        f"run_id: {run_id}\n"
        f"timestamp: {ts.isoformat()}\n"
        f"steps: {steps_summary}\n"
        f"artifacts changed: {artifacts_summary}\n"
        f"delta: {delta_line}\n"
        f"dry_run: {dry_run}\n"
    )

    # 8. Write memory entry — construct directly to set created_at from timestamp seam
    tags = ["run"] + (["dry_run"] if dry_run else [])
    entry = MemoryEntry(
        id=_new_id(),
        kind=MemoryKind.RUN,
        content=content,
        summary=summary,
        source="journal",
        tags=tags,
        metadata=metadata,
        created_at=ts,
        run_id=run_id,
    )
    memory.add(entry)

    # 9. Mirror to RUNLOG.md — swallow any write errors
    _append_runlog(root, run_id, ts, steps, artifacts_changed, delta_line, dry_run)


def _build_delta_line(artifacts_changed: list[str], state: FlowStateModel) -> str:
    """Build a concise one-line delta string."""
    if not artifacts_changed:
        return "no changes detected"
    n = len(artifacts_changed)
    sample = artifacts_changed[0] if artifacts_changed else ""
    if n == 1:
        return f"{sample} changed"
    return f"{sample} and {n - 1} other file(s) changed"


def _new_id() -> str:
    """Generate a 12-char hex ID matching MemoryEntry.create() convention."""
    from uuid import uuid4

    return uuid4().hex[:12]


def _append_runlog(
    root: Path,
    run_id: str,
    ts: datetime,
    steps: dict[str, str],
    artifacts_changed: list[str],
    delta_line: str,
    dry_run: bool,
) -> None:
    """Append a section to .planning/RUNLOG.md. Never raises."""
    try:
        runlog = root / ".planning" / "RUNLOG.md"
        runlog.parent.mkdir(parents=True, exist_ok=True)
        ts_iso = ts.isoformat()
        steps_str = ", ".join(f"{k}:{v}" for k, v in steps.items()) or "none"
        artifacts_str = ", ".join(artifacts_changed) if artifacts_changed else "none"
        with runlog.open("a") as fh:
            fh.write(f"\n## {ts_iso} — run {run_id}\n")
            fh.write(f"- steps: {steps_str}\n")
            fh.write(f"- artifacts changed: {artifacts_str}\n")
            fh.write("- decisions: (none this phase)\n")
            fh.write("- gotchas: (none this phase)\n")
            fh.write(f"- delta: {delta_line}\n")
            if dry_run:
                fh.write("- dry_run: true\n")
    except Exception:
        pass  # journal failure must never break the pipeline
