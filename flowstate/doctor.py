"""Doctor — pure-Python health check for a FlowState install.

No LLM calls. Each check returns a list of Diagnosis records; run_doctor
aggregates them and the CLI uses error-count for the exit code so doctor
composes in CI / pre-commit hooks.
"""

from __future__ import annotations

import hashlib
import logging
import os
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from flowstate.state import FlowStateModel, ToolStatus

logger = logging.getLogger(__name__)

STALE_RUNNING_HOURS = 24


@dataclass(frozen=True)
class Diagnosis:
    name: str
    severity: Literal["error", "warning", "info"]
    message: str
    fix_hint: str | None = None


def check_manifest_integrity(state: FlowStateModel, root: Path) -> list[Diagnosis]:
    """Verify every install_manifest entry exists on disk and checksum matches."""
    findings: list[Diagnosis] = []
    for entry in state.install_manifest:
        path = root / entry.path
        if not path.exists():
            findings.append(
                Diagnosis(
                    name="manifest_integrity",
                    severity="error",
                    message=f"Manifest file missing: {entry.path}",
                    fix_hint=(
                        "Run `flowstate repair` to regenerate context files, "
                        "or `flowstate init` to recreate."
                    ),
                )
            )
            continue
        if entry.checksum is not None and path.is_file():
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            if actual != entry.checksum:
                findings.append(
                    Diagnosis(
                        name="manifest_integrity",
                        severity="error",
                        message=f"Checksum drift: {entry.path}",
                        fix_hint=(
                            "Run `flowstate repair` to update manifest "
                            "checksums if change was intentional."
                        ),
                    )
                )
    return findings


def check_memory_schema(root: Path) -> list[Diagnosis]:
    """Verify memory.db exists with the FTS5 schema applied."""
    db_path = root / "memory.db"
    if not db_path.exists():
        return [
            Diagnosis(
                name="memory_schema",
                severity="error",
                message="memory.db not found",
                fix_hint="Run `flowstate repair` (recreates schema) or `flowstate init`.",
            )
        ]
    try:
        conn = sqlite3.connect(str(db_path))
        cur = conn.cursor()
        tables = {
            r[0]
            for r in cur.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table','view')"
            ).fetchall()
        }
        conn.close()
    except sqlite3.Error as e:
        return [
            Diagnosis(
                name="memory_schema",
                severity="error",
                message=f"memory.db unreadable: {e}",
                fix_hint="Run `flowstate repair --apply-destructive` to recreate.",
            )
        ]
    required = {"memories", "memories_fts", "schema_version"}
    missing = required - tables
    if missing:
        return [
            Diagnosis(
                name="memory_schema",
                severity="error",
                message=f"memory.db missing tables: {sorted(missing)}",
                fix_hint="Run `flowstate repair` to recreate FTS5 schema (idempotent).",
            )
        ]
    return []


def check_root_resolution(root: Path) -> list[Diagnosis]:
    """Verify the resolved project root exists and is a directory."""
    if not root.is_dir():
        return [
            Diagnosis(
                name="root_resolution",
                severity="error",
                message=f"Resolved root is not a directory: {root}",
                fix_hint=(
                    "Run `flowstate config clear-root` to reset, then re-run with explicit --root."
                ),
            )
        ]
    return []


def check_claude_cli() -> list[Diagnosis]:
    """Verify the claude CLI is locatable (env var or PATH)."""
    env_path = os.environ.get("FLOWSTATE_CLAUDE_BIN")
    if env_path and Path(env_path).exists():
        return []
    try:
        from flowstate.bridge import _find_claude

        bin_path = _find_claude()
        if bin_path:
            return []
        raise FileNotFoundError("claude CLI not found on PATH")
    except Exception as e:
        return [
            Diagnosis(
                name="claude_cli",
                severity="error",
                message=f"claude CLI not found: {e}",
                fix_hint="Install Claude Code or set FLOWSTATE_CLAUDE_BIN to the binary path.",
            )
        ]


def check_stale_status(state: FlowStateModel) -> list[Diagnosis]:
    """Warn on tools left in RUNNING status for >STALE_RUNNING_HOURS hours."""
    cutoff = datetime.now(UTC) - timedelta(hours=STALE_RUNNING_HOURS)
    findings: list[Diagnosis] = []
    for tool_name, ts in state.tools.items():
        if ts.status == ToolStatus.RUNNING and ts.started_at and ts.started_at < cutoff:
            findings.append(
                Diagnosis(
                    name="stale_status",
                    severity="warning",
                    message=f"Tool '{tool_name}' has status=Running for >{STALE_RUNNING_HOURS}h",
                    fix_hint="Run `flowstate repair` to reset to Blocked.",
                )
            )
    return findings


def check_orphan_files(state: FlowStateModel, root: Path) -> list[Diagnosis]:
    """Report files in .planning/ and research/ that aren't in install_manifest."""
    manifest_paths = {(root / e.path).resolve() for e in state.install_manifest}
    orphans: list[Path] = []
    for sub in (".planning", "research"):
        base = root / sub
        if base.is_dir():
            orphans.extend(
                p for p in base.rglob("*") if p.is_file() and p.resolve() not in manifest_paths
            )
    if not orphans:
        return []
    sample = ", ".join(str(p.relative_to(root)) for p in orphans[:5])
    more = f" (+{len(orphans) - 5} more)" if len(orphans) > 5 else ""
    return [
        Diagnosis(
            name="orphan_files",
            severity="info",
            message=f"{len(orphans)} orphan file(s) in .planning/ or research/: {sample}{more}",
            fix_hint=(
                "Run `flowstate fresh --force` to remove, "
                "or `flowstate repair --apply-destructive`."
            ),
        )
    ]


def run_doctor(state: FlowStateModel, root: Path) -> list[Diagnosis]:
    """Run every check; never raises. Returns aggregated diagnoses."""
    import flowstate.doctor as _self  # late binding so monkeypatches take effect

    checks = [
        ("manifest_integrity", lambda: _self.check_manifest_integrity(state, root)),
        ("memory_schema", lambda: _self.check_memory_schema(root)),
        ("root_resolution", lambda: _self.check_root_resolution(root)),
        ("claude_cli", lambda: _self.check_claude_cli()),
        ("stale_status", lambda: _self.check_stale_status(state)),
        ("orphan_files", lambda: _self.check_orphan_files(state, root)),
    ]
    findings: list[Diagnosis] = []
    for name, fn in checks:
        try:
            findings.extend(fn())
        except Exception as e:
            logger.exception("doctor check %s raised", name)
            findings.append(
                Diagnosis(
                    name=f"{name}_failed",
                    severity="error",
                    message=f"Check raised: {e}",
                    fix_hint=None,
                )
            )
    return findings
