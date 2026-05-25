"""Tests for install_manifest tracking on FlowStateModel."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from flowstate.state import (
    FlowStateModel,
    InstallEntry,
    _migrate_state,
    load_state,
    save_state,
)


class TestInstallEntry:
    def test_install_entry_validates_kind_literal(self):
        """Passing kind='invalid' raises ValidationError."""
        with pytest.raises(ValidationError):
            InstallEntry(
                path=".planning/PROJECT.md",
                owner="context",
                kind="invalid",  # type: ignore[arg-type]
            )

    def test_install_entry_defaults_checksum_none(self):
        """checksum defaults to None when not provided."""
        entry = InstallEntry(
            path="memory.db",
            owner="memory",
            kind="memory",
        )
        assert entry.checksum is None

    def test_install_entry_accepts_all_valid_kinds(self):
        for kind in ("config", "context", "memory", "research", "artifact"):
            entry = InstallEntry(path="x", owner="o", kind=kind)
            assert entry.kind == kind


class TestFlowStateModelManifest:
    def test_flowstate_model_default_manifest_empty(self):
        """Fresh FlowStateModel has install_manifest == []."""
        state = FlowStateModel()
        assert state.install_manifest == []

    def test_default_version_is_030(self):
        state = FlowStateModel()
        assert state.version == "0.3.0"

    def test_save_load_roundtrip_preserves_manifest(self, tmp_path: Path):
        """Manifest survives save/load 1:1."""
        state = FlowStateModel()
        now = datetime.now(UTC)
        state.install_manifest = [
            InstallEntry(
                path=".planning/PROJECT.md",
                owner="context",
                kind="context",
                created_at=now,
                checksum="a" * 64,
            ),
            InstallEntry(
                path="memory.db",
                owner="memory",
                kind="memory",
                created_at=now,
                checksum=None,
            ),
            InstallEntry(
                path="research/report.md",
                owner="research",
                kind="research",
                created_at=now,
                checksum="b" * 64,
            ),
        ]

        save_state(state, tmp_path)
        loaded = load_state(tmp_path)

        assert len(loaded.install_manifest) == 3
        assert loaded.install_manifest[0].path == ".planning/PROJECT.md"
        assert loaded.install_manifest[0].kind == "context"
        assert loaded.install_manifest[0].checksum == "a" * 64
        assert loaded.install_manifest[1].path == "memory.db"
        assert loaded.install_manifest[1].checksum is None
        assert loaded.install_manifest[2].path == "research/report.md"


class TestMigration:
    def test_migrate_v020_adds_empty_manifest(self):
        """v0.2.0 data without install_manifest gets one (empty) and bumps to 0.3.0."""
        data = {
            "version": "0.2.0",
            "tools": {
                "research": {"status": "ready"},
                "strategy": {"status": "ready"},
                "gsd": {"status": "ready"},
                "discipline": {"status": "ready"},
            },
        }
        migrated = _migrate_state(data)
        assert migrated["version"] == "0.3.0"
        assert migrated["install_manifest"] == []

    def test_migrate_v030_noop(self):
        """v0.3.0 data is not modified."""
        data = {
            "version": "0.3.0",
            "tools": {},
            "install_manifest": [
                {
                    "path": "x",
                    "owner": "o",
                    "kind": "config",
                    "created_at": datetime.now(UTC).isoformat(),
                    "checksum": None,
                }
            ],
        }
        migrated = _migrate_state(data)
        assert migrated["version"] == "0.3.0"
        assert len(migrated["install_manifest"]) == 1

    def test_load_backfills_manifest_from_disk(self, tmp_path: Path):
        """Loading a v0.2.0 flowstate.json on a project with existing files backfills manifest."""
        planning = tmp_path / ".planning"
        planning.mkdir()
        (planning / "PROJECT.md").write_text("# Project")
        (planning / "ROADMAP.md").write_text("# Roadmap")
        (planning / "config.json").write_text("{}")

        # Write a v0.2.0 state file (no install_manifest key)
        old_state = {
            "version": "0.2.0",
            "tools": {
                "research": {"status": "ready"},
                "strategy": {"status": "ready"},
                "gsd": {"status": "ready"},
                "discipline": {"status": "ready"},
            },
            "artifacts": {},
        }
        (tmp_path / "flowstate.json").write_text(json.dumps(old_state))

        state = load_state(tmp_path)

        paths = [e.path for e in state.install_manifest]
        assert ".planning/PROJECT.md" in paths
        assert ".planning/ROADMAP.md" in paths
        assert ".planning/config.json" in paths
        # version was migrated
        assert state.version == "0.3.0"

        # PROJECT.md entry kind
        project_entry = next(e for e in state.install_manifest if e.path == ".planning/PROJECT.md")
        assert project_entry.kind == "context"
        # config.json entry kind
        cfg_entry = next(e for e in state.install_manifest if e.path == ".planning/config.json")
        assert cfg_entry.kind == "config"


class TestPipelineRegistration:
    def test_memory_db_registered_on_pipeline_start(self, tmp_path: Path):
        """run_pipeline creates memory.db and registers it on the manifest."""
        from flowstate.orchestrator import run_pipeline

        state = FlowStateModel()
        state.preferences.dry_run = True
        state.interview.research_focus = "testing"
        state.interview.core_problem = "test problem"

        run_pipeline(state, tmp_path)

        memory_entries = [e for e in state.install_manifest if e.path == "memory.db"]
        assert len(memory_entries) >= 1, "expected memory.db entry in install_manifest"
        entry = memory_entries[0]
        assert entry.kind == "memory"
        assert entry.checksum is None
        assert entry.owner == "memory"

    def test_memory_db_registration_is_idempotent(self, tmp_path: Path):
        """Re-running pipeline does not duplicate memory.db entry."""
        from flowstate.orchestrator import run_pipeline

        state = FlowStateModel()
        state.preferences.dry_run = True
        state.interview.research_focus = "x"
        state.interview.core_problem = "y"

        run_pipeline(state, tmp_path)
        run_pipeline(state, tmp_path)

        memory_entries = [e for e in state.install_manifest if e.path == "memory.db"]
        assert len(memory_entries) == 1
