"""Tests for flowstate.doctor — pure-Python health checks."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from flowstate.doctor import (
    STALE_RUNNING_HOURS,
    Diagnosis,
    check_claude_cli,
    check_manifest_integrity,
    check_memory_schema,
    check_orphan_files,
    check_root_resolution,
    check_stale_status,
    run_doctor,
)
from flowstate.memory import MemoryStore
from flowstate.state import FlowStateModel, InstallEntry, ToolStatus


class TestDiagnosis:
    def test_is_frozen(self):
        d = Diagnosis(name="x", severity="info", message="m")
        with pytest.raises(Exception):
            d.name = "y"  # type: ignore[misc]

    def test_default_fix_hint_none(self):
        d = Diagnosis(name="x", severity="info", message="m")
        assert d.fix_hint is None


def _make_entry(path: str, checksum: str | None = None) -> InstallEntry:
    return InstallEntry(
        path=path,
        owner="context",
        kind="context",
        created_at=datetime.now(UTC),
        checksum=checksum,
    )


class TestManifestIntegrity:
    def test_healthy_returns_empty(self, tmp_path: Path):
        planning = tmp_path / ".planning"
        planning.mkdir()
        p = planning / "PROJECT.md"
        p.write_text("# hello")
        checksum = hashlib.sha256(p.read_bytes()).hexdigest()
        state = FlowStateModel()
        state.install_manifest.append(_make_entry(".planning/PROJECT.md", checksum))
        assert check_manifest_integrity(state, tmp_path) == []

    def test_missing_file_returns_error(self, tmp_path: Path):
        state = FlowStateModel()
        state.install_manifest.append(_make_entry(".planning/PROJECT.md", "abc" * 22))
        findings = check_manifest_integrity(state, tmp_path)
        assert len(findings) == 1
        assert findings[0].severity == "error"
        assert findings[0].name == "manifest_integrity"
        assert "missing" in findings[0].message.lower()

    def test_checksum_drift_returns_error(self, tmp_path: Path):
        planning = tmp_path / ".planning"
        planning.mkdir()
        p = planning / "PROJECT.md"
        p.write_text("# original")
        state = FlowStateModel()
        # Record a wrong checksum
        state.install_manifest.append(_make_entry(".planning/PROJECT.md", "0" * 64))
        findings = check_manifest_integrity(state, tmp_path)
        assert len(findings) == 1
        assert findings[0].severity == "error"
        assert "drift" in findings[0].message.lower()

    def test_none_checksum_skipped(self, tmp_path: Path):
        (tmp_path / "memory.db").write_bytes(b"binary")
        state = FlowStateModel()
        state.install_manifest.append(
            InstallEntry(
                path="memory.db",
                owner="memory",
                kind="memory",
                created_at=datetime.now(UTC),
                checksum=None,
            )
        )
        assert check_manifest_integrity(state, tmp_path) == []


class TestMemorySchema:
    def test_missing_db_returns_error(self, tmp_path: Path):
        findings = check_memory_schema(tmp_path)
        assert len(findings) == 1
        assert findings[0].severity == "error"
        assert findings[0].name == "memory_schema"

    def test_healthy_db_returns_empty(self, tmp_path: Path):
        with MemoryStore(root=tmp_path):
            pass
        assert check_memory_schema(tmp_path) == []

    def test_corrupt_db_returns_error(self, tmp_path: Path):
        db = tmp_path / "memory.db"
        db.write_bytes(b"this is not a sqlite database")
        findings = check_memory_schema(tmp_path)
        assert len(findings) == 1
        assert findings[0].severity == "error"
        assert findings[0].name == "memory_schema"


class TestRootResolution:
    def test_missing_dir_returns_error(self, tmp_path: Path):
        findings = check_root_resolution(tmp_path / "does-not-exist")
        assert len(findings) == 1
        assert findings[0].severity == "error"

    def test_real_dir_returns_empty(self, tmp_path: Path):
        assert check_root_resolution(tmp_path) == []


class TestClaudeCli:
    def test_env_var_set_to_existing_returns_empty(self, monkeypatch, tmp_path: Path):
        fake = tmp_path / "fake_claude"
        fake.write_text("#!/bin/sh\nexit 0\n")
        fake.chmod(0o755)
        monkeypatch.setenv("FLOWSTATE_CLAUDE_BIN", str(fake))
        assert check_claude_cli() == []

    def test_no_claude_no_env_returns_error(self, monkeypatch):
        monkeypatch.delenv("FLOWSTATE_CLAUDE_BIN", raising=False)

        def _raise() -> str:
            raise FileNotFoundError("not installed")

        monkeypatch.setattr("flowstate.bridge._find_claude", _raise)
        findings = check_claude_cli()
        assert len(findings) == 1
        assert findings[0].severity == "error"
        assert findings[0].name == "claude_cli"


class TestStaleStatus:
    def test_no_stale_returns_empty(self):
        state = FlowStateModel()
        assert check_stale_status(state) == []

    def test_stale_running_returns_warning(self):
        state = FlowStateModel()
        state.tools["research"].status = ToolStatus.RUNNING
        state.tools["research"].started_at = datetime.now(UTC) - timedelta(hours=48)
        findings = check_stale_status(state)
        assert len(findings) == 1
        assert findings[0].severity == "warning"
        assert findings[0].name == "stale_status"
        assert "research" in findings[0].message

    def test_recent_running_returns_empty(self):
        state = FlowStateModel()
        state.tools["research"].status = ToolStatus.RUNNING
        state.tools["research"].started_at = datetime.now(UTC) - timedelta(hours=1)
        assert check_stale_status(state) == []


class TestOrphanFiles:
    def test_no_orphans_returns_empty(self, tmp_path: Path):
        state = FlowStateModel()
        assert check_orphan_files(state, tmp_path) == []

    def test_orphans_returned_as_info(self, tmp_path: Path):
        planning = tmp_path / ".planning"
        planning.mkdir()
        (planning / "ORPHAN.md").write_text("# orphan")
        state = FlowStateModel()
        findings = check_orphan_files(state, tmp_path)
        assert len(findings) == 1
        assert findings[0].name == "orphan_files"
        assert "ORPHAN.md" in findings[0].message

    def test_orphan_severity_is_info(self, tmp_path: Path):
        planning = tmp_path / ".planning"
        planning.mkdir()
        (planning / "X.md").write_text("x")
        state = FlowStateModel()
        findings = check_orphan_files(state, tmp_path)
        assert findings[0].severity == "info"


class TestRunDoctor:
    def test_healthy_install_returns_empty(self, tmp_path: Path, monkeypatch):
        fake = tmp_path / "fake_claude"
        fake.write_text("#!/bin/sh\nexit 0\n")
        fake.chmod(0o755)
        monkeypatch.setenv("FLOWSTATE_CLAUDE_BIN", str(fake))

        with MemoryStore(root=tmp_path):
            pass

        state = FlowStateModel()
        # No manifest entries → no checks, healthy
        assert run_doctor(state, tmp_path) == []

    def test_aggregates_multiple_findings(self, tmp_path: Path, monkeypatch):
        monkeypatch.delenv("FLOWSTATE_CLAUDE_BIN", raising=False)

        def _raise() -> str:
            raise FileNotFoundError("none")

        monkeypatch.setattr("flowstate.bridge._find_claude", _raise)

        # tmp_path has no memory.db → memory_schema error
        # claude_cli error from monkeypatch
        state = FlowStateModel()
        state.install_manifest.append(_make_entry(".planning/MISSING.md", "0" * 64))
        findings = run_doctor(state, tmp_path)
        names = {f.name for f in findings}
        assert "manifest_integrity" in names
        assert "memory_schema" in names
        assert "claude_cli" in names

    def test_check_exception_becomes_error_diagnosis(self, tmp_path: Path, monkeypatch):
        def _raise(state, root):
            raise RuntimeError("boom")

        monkeypatch.setattr("flowstate.doctor.check_manifest_integrity", _raise)
        # Ensure claude check passes so we can isolate
        fake = tmp_path / "fake_claude"
        fake.write_text("#!/bin/sh\nexit 0\n")
        fake.chmod(0o755)
        monkeypatch.setenv("FLOWSTATE_CLAUDE_BIN", str(fake))
        with MemoryStore(root=tmp_path):
            pass

        state = FlowStateModel()
        findings = run_doctor(state, tmp_path)
        names = {f.name for f in findings}
        assert "manifest_integrity_failed" in names

    def test_stale_running_hours_constant(self):
        assert STALE_RUNNING_HOURS == 24
