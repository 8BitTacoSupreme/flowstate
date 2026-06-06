"""Repair — apply the safe subset of doctor's diagnoses; destructive fixes gated.

Safe fixes (always applied by `flowstate repair`):
  - Regenerate missing context files from state.interview
  - Recreate memory.db FTS5 schema (idempotent CREATE IF NOT EXISTS)
  - Reset stale Running statuses to Blocked
  - Update drifted checksums on install_manifest entries (when file still exists)

Destructive fixes (require --apply-destructive):
  - Delete orphan files (not in install_manifest)
  - Drop / recreate memory.db when unreadable
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from flowstate.context import write_context_files
from flowstate.doctor import Diagnosis
from flowstate.memory import MemoryStore
from flowstate.state import FlowStateModel, ToolStatus

KNOWN_CONTEXT_FILES = {
    ".planning/PROJECT.md",
    ".planning/ROADMAP.md",
    ".planning/config.json",
    ".claude/CLAUDE.md",
    "research/brief.md",
}


def apply_safe_fixes(
    state: FlowStateModel,
    root: Path,
    diagnoses: list[Diagnosis],
) -> list[str]:
    """Apply the safe subset of fixes. Returns human-readable descriptions."""
    applied: list[str] = []

    # 1. Regenerate missing context files
    missing_context = [
        d
        for d in diagnoses
        if d.name == "manifest_integrity"
        and "missing" in d.message.lower()
        and any(known in d.message for known in KNOWN_CONTEXT_FILES)
    ]
    if missing_context:
        created = write_context_files(state, root)
        applied.append(f"regenerated context files: {[p.name for p in created]}")

    # 2. Recreate memory schema (idempotent CREATE IF NOT EXISTS)
    memory_schema_diagnoses = [d for d in diagnoses if d.name == "memory_schema"]
    safe_memory = [d for d in memory_schema_diagnoses if "unreadable" not in d.message.lower()]
    if safe_memory:
        with MemoryStore(root=root):
            pass
        applied.append("recreated memory.db schema (idempotent)")

    # 3. Reset stale Running statuses
    stale = [d for d in diagnoses if d.name == "stale_status"]
    reset_tools: list[str] = []
    for d in stale:
        match = re.search(r"Tool '([^']+)'", d.message)
        if match:
            tool_name = match.group(1)
            if tool_name in state.tools:
                state.tools[tool_name].status = ToolStatus.BLOCKED
                state.tools[tool_name].error = "reset by repair (stale Running)"
                reset_tools.append(tool_name)
    if reset_tools:
        applied.append(f"reset stale Running statuses: {reset_tools}")

    # 4. Update drifted checksums (file exists, hash changed).
    #
    # IMPORTANT: InstallEntry is a Pydantic v2 BaseModel. In-place assignment
    # (entry.checksum = "...") raises ValidationError on validate-on-assignment
    # models. Use model_copy(update=...) to produce a new entry and rebuild
    # the manifest list.
    drift = [
        d for d in diagnoses if d.name == "manifest_integrity" and "drift" in d.message.lower()
    ]
    updated_paths: list[str] = []
    if drift:
        new_manifest = []
        for entry in state.install_manifest:
            path = root / entry.path
            if not path.is_file() or entry.checksum is None:
                new_manifest.append(entry)
                continue
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            if actual != entry.checksum:
                new_manifest.append(entry.model_copy(update={"checksum": actual}))
                updated_paths.append(entry.path)
            else:
                new_manifest.append(entry)
        if updated_paths:
            state.install_manifest = new_manifest
            applied.append(f"updated drifted checksums: {updated_paths}")

    return applied


def apply_destructive_fixes(
    state: FlowStateModel,
    root: Path,
    diagnoses: list[Diagnosis],
) -> list[str]:
    """Apply destructive fixes. Caller must opt in by passing diagnoses to this fn."""
    applied: list[str] = []

    # 1. Delete orphan files
    if any(d.name == "orphan_files" for d in diagnoses):
        manifest_paths = {(root / e.path).resolve() for e in state.install_manifest}
        deleted: list[str] = []
        for sub in (".planning", "research"):
            base = root / sub
            if not base.is_dir():
                continue
            for p in base.rglob("*"):
                if p.is_file() and p.resolve() not in manifest_paths:
                    p.unlink()
                    deleted.append(str(p.relative_to(root)))
        if deleted:
            applied.append(f"deleted orphan files: {deleted}")

    # 2. Recreate memory.db when unreadable
    unreadable = [
        d for d in diagnoses if d.name == "memory_schema" and "unreadable" in d.message.lower()
    ]
    if unreadable:
        db_path = root / "memory.db"
        if db_path.exists():
            db_path.unlink()
        with MemoryStore(root=root):
            pass
        applied.append("recreated memory.db (was unreadable)")

    return applied
