"""Tests for flowstate.repair — safe-by-default fixer."""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

from flowstate.doctor import Diagnosis
from flowstate.memory import MemoryStore
from flowstate.repair import (
    KNOWN_CONTEXT_FILES,
    apply_destructive_fixes,
    apply_safe_fixes,
)
from flowstate.state import FlowStateModel, InstallEntry, ToolStatus


def _entry(path: str, kind: str = "context", checksum: str | None = None) -> InstallEntry:
    return InstallEntry(
        path=path,
        owner="context",
        kind=kind,  # type: ignore[arg-type]
        created_at=datetime.now(UTC),
        checksum=checksum,
    )


class TestApplySafeFixes:
    def test_no_diagnoses_returns_empty(self, tmp_path: Path):
        state = FlowStateModel()
        assert apply_safe_fixes(state, tmp_path, []) == []

    def test_missing_context_file_regenerated(self, tmp_path: Path):
        state = FlowStateModel()
        state.interview.core_problem = "test problem"
        state.interview.ten_x_vision = "test vision"
        d = Diagnosis(
            name="manifest_integrity",
            severity="error",
            message="Manifest file missing: .planning/PROJECT.md",
        )
        applied = apply_safe_fixes(state, tmp_path, [d])
        assert (tmp_path / ".planning" / "PROJECT.md").exists()
        assert any("regenerated context files" in line for line in applied)

    def test_memory_schema_diagnosis_recreates_schema(self, tmp_path: Path):
        state = FlowStateModel()
        d = Diagnosis(
            name="memory_schema",
            severity="error",
            message="memory.db not found",
        )
        applied = apply_safe_fixes(state, tmp_path, [d])
        assert any("recreated memory.db schema" in line for line in applied)
        assert (tmp_path / "memory.db").exists()
        conn = sqlite3.connect(str(tmp_path / "memory.db"))
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        conn.close()
        assert "memories" in tables

    def test_stale_status_resets_to_blocked(self, tmp_path: Path):
        state = FlowStateModel()
        state.tools["research"].status = ToolStatus.RUNNING
        state.tools["research"].started_at = datetime.now(UTC) - timedelta(hours=48)
        d = Diagnosis(
            name="stale_status",
            severity="warning",
            message="Tool 'research' has status=Running for >24h",
        )
        applied = apply_safe_fixes(state, tmp_path, [d])
        assert state.tools["research"].status == ToolStatus.BLOCKED
        assert state.tools["research"].error is not None
        assert "reset by repair" in state.tools["research"].error
        assert any("reset stale Running statuses" in line for line in applied)

    def test_checksum_drift_updates_entry(self, tmp_path: Path):
        planning = tmp_path / ".planning"
        planning.mkdir()
        p = planning / "PROJECT.md"
        p.write_text("# new content")
        actual = hashlib.sha256(p.read_bytes()).hexdigest()
        wrong = "0" * 64

        state = FlowStateModel()
        state.install_manifest.append(_entry(".planning/PROJECT.md", checksum=wrong))
        d = Diagnosis(
            name="manifest_integrity",
            severity="error",
            message="Checksum drift: .planning/PROJECT.md",
        )
        # Must NOT raise ValidationError
        applied = apply_safe_fixes(state, tmp_path, [d])
        # Find the entry — should now have the actual checksum
        entry = next(e for e in state.install_manifest if e.path == ".planning/PROJECT.md")
        assert entry.checksum == actual
        assert any("updated drifted checksums" in line for line in applied)

    def test_safe_fixes_does_not_delete_orphans(self, tmp_path: Path):
        planning = tmp_path / ".planning"
        planning.mkdir()
        orphan = planning / "ORPHAN.md"
        orphan.write_text("# orphan")
        state = FlowStateModel()
        d = Diagnosis(
            name="orphan_files",
            severity="info",
            message="1 orphan file(s) in .planning/: .planning/ORPHAN.md",
        )
        apply_safe_fixes(state, tmp_path, [d])
        assert orphan.exists()


class TestApplyDestructiveFixes:
    def test_orphan_files_deleted(self, tmp_path: Path):
        planning = tmp_path / ".planning"
        planning.mkdir()
        orphan = planning / "ORPHAN.md"
        orphan.write_text("# orphan")
        state = FlowStateModel()
        d = Diagnosis(
            name="orphan_files",
            severity="info",
            message="1 orphan file(s): .planning/ORPHAN.md",
        )
        applied = apply_destructive_fixes(state, tmp_path, [d])
        assert not orphan.exists()
        assert any("deleted orphan files" in line for line in applied)

    def test_unreadable_memory_db_recreated(self, tmp_path: Path):
        (tmp_path / "memory.db").write_bytes(b"garbage bytes here")
        state = FlowStateModel()
        d = Diagnosis(
            name="memory_schema",
            severity="error",
            message="memory.db unreadable: file is not a database",
        )
        applied = apply_destructive_fixes(state, tmp_path, [d])
        conn = sqlite3.connect(str(tmp_path / "memory.db"))
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        conn.close()
        assert "memories" in tables
        assert any("recreated memory.db" in line for line in applied)

    def test_destructive_skipped_without_matching_diagnosis(self, tmp_path: Path):
        state = FlowStateModel()
        assert apply_destructive_fixes(state, tmp_path, []) == []


class TestKnownContextFiles:
    def test_includes_five_expected_paths(self):
        assert ".planning/PROJECT.md" in KNOWN_CONTEXT_FILES
        assert ".planning/ROADMAP.md" in KNOWN_CONTEXT_FILES
        assert ".planning/config.json" in KNOWN_CONTEXT_FILES
        assert ".claude/CLAUDE.md" in KNOWN_CONTEXT_FILES
        assert "research/brief.md" in KNOWN_CONTEXT_FILES
