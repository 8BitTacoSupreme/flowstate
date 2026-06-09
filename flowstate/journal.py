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

    # 1. Idempotency guard — indexed COUNT query (scale-independent, hits idx_memories_run_id)
    if memory.count(MemoryKind.RUN, run_id=run_id) > 0:
        return

    # 2. Fetch prior RUN entry for delta computation (separate from idempotency guard)
    existing = memory.get_by_kind(MemoryKind.RUN, limit=1)
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
        delta_line = _build_delta_line(artifacts_changed)
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
    # Populate gotchas slot from INSIGHT entries captured this run
    try:
        gotcha_entries = memory.get_by_kind(MemoryKind.INSIGHT, limit=200)
        this_run_sigs = [
            e.metadata.get("signature", "")
            for e in gotcha_entries
            if run_id and e.run_id == run_id and "gotcha" in e.tags
        ]
    except Exception:
        this_run_sigs = []

    metadata: dict[str, Any] = {
        "run_id": run_id,
        "snapshot": current_snapshot,
        "steps": steps,
        "artifacts_changed": artifacts_changed,
        "decisions": [],
        "gotchas": this_run_sigs,
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
    try:
        memory.add(entry)
    except Exception:
        return  # memory write failed; best-effort — never raise into pipeline

    # 9. Mirror to RUNLOG.md — swallow any write errors
    _append_runlog(root, run_id, ts, steps, artifacts_changed, delta_line, dry_run, this_run_sigs)


def append_verify_entry(
    memory: MemoryStore,
    root: Path,
    results: list[Any],
    *,
    timestamp: datetime | None = None,
) -> None:
    """Write one MemoryKind.RUN entry tagged ["verify"] for a standalone verify run.

    Mirrors the result to .planning/RUNLOG.md as an append-only human-readable trail.
    Never raises — journal failures must not break the caller.
    Each CLI invocation is a distinct event; no idempotency guard is applied.
    """
    ts = timestamp or datetime.now(UTC)

    try:
        # Derive counts from results by status (duck-typed: .status and .gate attributes)
        gates_passed = sum(1 for r in results if r.status == "pass")
        gates_failed = sum(1 for r in results if r.status == "fail")
        gates_skipped = sum(1 for r in results if r.status == "skip")
        failed_signatures = [r.gate for r in results if r.status == "fail"]
    except Exception:
        return  # malformed results; nothing safe to journal

    metadata: dict[str, Any] = {
        "verify": True,
        "gates_passed": gates_passed,
        "gates_failed": gates_failed,
        "gates_skipped": gates_skipped,
        "failed_signatures": failed_signatures,
    }

    summary = f"verify: {gates_passed} pass / {gates_failed} fail / {gates_skipped} skip"
    failed_str = ", ".join(failed_signatures) if failed_signatures else "none"
    content = (
        f"timestamp: {ts.isoformat()}\n"
        f"gates: {gates_passed} pass / {gates_failed} fail / {gates_skipped} skip\n"
        f"failed: {failed_str}\n"
    )

    entry = MemoryEntry(
        id=_new_id(),
        kind=MemoryKind.RUN,
        content=content,
        summary=summary,
        source="journal",
        tags=["verify"],
        metadata=metadata,
        created_at=ts,
        run_id="",
    )
    try:
        memory.add(entry)
    except Exception:
        return  # memory write failed; best-effort — never raise into caller

    # Mirror to RUNLOG.md — swallow any write errors
    _append_verify_runlog(root, ts, gates_passed, gates_failed, gates_skipped, failed_signatures)


def _append_verify_runlog(
    root: Path,
    ts: datetime,
    passed: int,
    failed: int,
    skipped: int,
    failed_signatures: list[str],
) -> None:
    """Append a verify section to .planning/RUNLOG.md. Never raises."""
    try:
        runlog = root / ".planning" / "RUNLOG.md"
        runlog.parent.mkdir(parents=True, exist_ok=True)
        with runlog.open("a") as fh:
            fh.write(f"\n## {ts.isoformat()} — verify\n")
            fh.write(f"- gates: {passed} pass / {failed} fail / {skipped} skip\n")
            if failed_signatures:
                failed_str = ", ".join(failed_signatures)
                fh.write(f"- failed: {failed_str}\n")
    except Exception:
        pass  # journal failure must never break the caller


def _build_delta_line(artifacts_changed: list[str]) -> str:
    """Build a concise one-line delta string."""
    if not artifacts_changed:
        return "no changes detected"
    n = len(artifacts_changed)
    sample = artifacts_changed[0]  # guaranteed non-empty — line above guards the empty case
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
    gotchas: list[str] | None = None,
) -> None:
    """Append a section to .planning/RUNLOG.md. Never raises."""
    try:
        runlog = root / ".planning" / "RUNLOG.md"
        runlog.parent.mkdir(parents=True, exist_ok=True)
        ts_iso = ts.isoformat()
        steps_str = ", ".join(f"{k}:{v}" for k, v in steps.items()) or "none"
        artifacts_str = ", ".join(artifacts_changed) if artifacts_changed else "none"
        gotchas_list = gotchas or []
        gotchas_str = ", ".join(gotchas_list) if gotchas_list else "(none this run)"
        with runlog.open("a") as fh:
            fh.write(f"\n## {ts_iso} — run {run_id}\n")
            fh.write(f"- steps: {steps_str}\n")
            fh.write(f"- artifacts changed: {artifacts_str}\n")
            fh.write("- decisions: (none this run)\n")
            fh.write(f"- gotchas: {gotchas_str}\n")
            fh.write(f"- delta: {delta_line}\n")
            if dry_run:
                fh.write("- dry_run: true\n")
    except Exception:
        pass  # journal failure must never break the pipeline
