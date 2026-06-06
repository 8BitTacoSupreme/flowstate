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
        for kind in ("config", "context", "memory", "research", "artifact", "pack", "fixture"):
            entry = InstallEntry(path="x", owner="o", kind=kind)
            assert entry.kind == kind


class TestFlowStateModelManifest:
    def test_flowstate_model_default_manifest_empty(self):
        """Fresh FlowStateModel has install_manifest == []."""
        state = FlowStateModel()
        assert state.install_manifest == []

    def test_default_version_is_040(self):
        state = FlowStateModel()
        assert state.version == "0.4.0"

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
        """v0.2.0 data without install_manifest gets one (empty) and bumps to 0.4.0."""
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
        assert migrated["version"] == "0.4.0"
        assert migrated["install_manifest"] == []

    def test_migrate_v030_noop(self):
        """v0.3.0 data is migrated to 0.4.0 (guard no longer short-circuits at 0.3.0)."""
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
        assert migrated["version"] == "0.4.0"
        assert len(migrated["install_manifest"]) == 1

    def test_migrate_v030_to_v040(self):
        """v0.3.0 state migrates to v0.4.0; existing entries are preserved unchanged."""
        data = {
            "version": "0.3.0",
            "tools": {
                "research": {"status": "ready"},
                "strategy": {"status": "ready"},
                "gsd": {"status": "ready"},
                "discipline": {"status": "ready"},
            },
            "install_manifest": [],
        }
        migrated = _migrate_state(data)
        assert migrated["version"] == "0.4.0"

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
        # version was migrated (v0.2.0 → v0.3.0 → v0.4.0)
        assert state.version == "0.4.0"

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


class TestFreshCommand:
    """Tests for the manifest-aware `flowstate fresh` command."""

    def _make_state_with_manifest(self, tmp_path: Path, entries: list[dict]) -> None:
        """Write a flowstate.json populated with the given manifest entries."""
        from flowstate.state import FlowStateModel, InstallEntry, save_state

        state = FlowStateModel()
        state.install_manifest = [InstallEntry(**e) for e in entries]
        save_state(state, tmp_path)

    def test_fresh_removes_only_manifest_files(self, tmp_path: Path):
        """`fresh --yes` removes manifest files only; orphans are reported but left."""
        from click.testing import CliRunner

        from flowstate.cli import main

        # Manifest tracks PROJECT.md only
        planning = tmp_path / ".planning"
        planning.mkdir()
        (planning / "PROJECT.md").write_text("# Project")
        (planning / "EXTRA.md").write_text("# Orphan")  # not in manifest

        self._make_state_with_manifest(
            tmp_path,
            [
                {
                    "path": ".planning/PROJECT.md",
                    "owner": "context",
                    "kind": "context",
                    "created_at": datetime.now(UTC),
                    "checksum": None,
                }
            ],
        )

        runner = CliRunner()
        result = runner.invoke(main, ["fresh", "--yes", "--root", str(tmp_path)])
        assert result.exit_code == 0, result.output
        # Manifest file removed
        assert not (planning / "PROJECT.md").exists()
        # Orphan preserved
        assert (planning / "EXTRA.md").exists()
        # Orphans section was reported
        assert "Orphans" in result.output

    def test_fresh_force_removes_orphans(self, tmp_path: Path):
        """`fresh --yes --force` removes both manifest files and orphans."""
        from click.testing import CliRunner

        from flowstate.cli import main

        planning = tmp_path / ".planning"
        planning.mkdir()
        (planning / "PROJECT.md").write_text("# Project")
        (planning / "EXTRA.md").write_text("# Orphan")

        self._make_state_with_manifest(
            tmp_path,
            [
                {
                    "path": ".planning/PROJECT.md",
                    "owner": "context",
                    "kind": "context",
                    "created_at": datetime.now(UTC),
                    "checksum": None,
                }
            ],
        )

        runner = CliRunner()
        result = runner.invoke(main, ["fresh", "--yes", "--force", "--root", str(tmp_path)])
        assert result.exit_code == 0, result.output
        assert not (planning / "PROJECT.md").exists()
        assert not (planning / "EXTRA.md").exists()

    def test_fresh_skips_missing_manifest_files(self, tmp_path: Path):
        """Manifest entries that don't exist on disk are skipped silently."""
        from click.testing import CliRunner

        from flowstate.cli import main

        self._make_state_with_manifest(
            tmp_path,
            [
                {
                    "path": ".planning/GONE.md",
                    "owner": "context",
                    "kind": "context",
                    "created_at": datetime.now(UTC),
                    "checksum": "deadbeef",
                }
            ],
        )

        runner = CliRunner()
        result = runner.invoke(main, ["fresh", "--yes", "--root", str(tmp_path)])
        assert result.exit_code == 0, result.output

    def test_fresh_warns_on_checksum_mismatch(self, tmp_path: Path):
        """Manifest file whose checksum changed surfaces a 'modified' warning."""
        from click.testing import CliRunner

        from flowstate.cli import main

        planning = tmp_path / ".planning"
        planning.mkdir()
        (planning / "PROJECT.md").write_text("# DRIFTED")

        self._make_state_with_manifest(
            tmp_path,
            [
                {
                    "path": ".planning/PROJECT.md",
                    "owner": "context",
                    "kind": "context",
                    "created_at": datetime.now(UTC),
                    "checksum": "a" * 64,  # doesn't match the actual file
                }
            ],
        )

        runner = CliRunner()
        result = runner.invoke(main, ["fresh", "--yes", "--root", str(tmp_path)])
        assert result.exit_code == 0, result.output
        assert "modified" in result.output.lower()

    def test_fresh_cancels_on_no(self, tmp_path: Path):
        """Without --yes, answering 'n' to the prompt cancels deletion."""
        from click.testing import CliRunner

        from flowstate.cli import main

        planning = tmp_path / ".planning"
        planning.mkdir()
        (planning / "PROJECT.md").write_text("# Project")

        self._make_state_with_manifest(
            tmp_path,
            [
                {
                    "path": ".planning/PROJECT.md",
                    "owner": "context",
                    "kind": "context",
                    "created_at": datetime.now(UTC),
                    "checksum": None,
                }
            ],
        )

        runner = CliRunner()
        result = runner.invoke(main, ["fresh", "--root", str(tmp_path)], input="n\n")
        assert result.exit_code == 0, result.output
        assert "Cancelled" in result.output
        # File survived
        assert (planning / "PROJECT.md").exists()

    def test_fresh_works_on_empty_directory(self, tmp_path: Path):
        """`fresh --yes` on a fresh directory (no flowstate.json) exits cleanly."""
        from click.testing import CliRunner

        from flowstate.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["fresh", "--yes", "--root", str(tmp_path)])
        assert result.exit_code == 0, result.output
        assert "Nothing to clean" in result.output
