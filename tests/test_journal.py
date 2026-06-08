"""Tests for flowstate.journal — append_run_entry behavior."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from flowstate.journal import append_run_entry
from flowstate.memory import MemoryKind, MemoryStore
from flowstate.state import FlowStateModel, InstallEntry, ToolStatus, update_tool

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def store(tmp_path: Path) -> MemoryStore:
    with MemoryStore(root=tmp_path) as s:
        yield s


@pytest.fixture()
def state_with_manifest() -> FlowStateModel:
    """FlowStateModel with a seeded install_manifest for diff testing."""
    state = FlowStateModel()
    state.install_manifest = [
        InstallEntry(
            path="research/report.md",
            owner="research",
            kind="research",
            created_at=datetime.now(UTC),
            checksum="aabbcc112233",
        ),
        InstallEntry(
            path=".planning/ROADMAP.md",
            owner="gsd",
            kind="artifact",
            created_at=datetime.now(UTC),
            checksum="ddeeff445566",
        ),
        InstallEntry(
            path="memory.db",
            owner="memory",
            kind="memory",
            created_at=datetime.now(UTC),
            checksum=None,  # excluded from snapshot
        ),
    ]
    for tool in ("research", "strategy", "gsd", "discipline"):
        update_tool(state, tool, status=ToolStatus.COMPLETED)
    return state


FIXED_TS = datetime(2026, 6, 8, 12, 0, 0, tzinfo=UTC)


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestFirstRun:
    def test_first_run_creates_one_entry(self, store: MemoryStore, state_with_manifest, tmp_path):
        append_run_entry(store, state_with_manifest, "aaa111", root=tmp_path, timestamp=FIXED_TS)
        assert store.count(MemoryKind.RUN) == 1

    def test_first_run_delta_line_says_first_run(
        self, store: MemoryStore, state_with_manifest, tmp_path
    ):
        append_run_entry(store, state_with_manifest, "aaa111", root=tmp_path, timestamp=FIXED_TS)
        entries = store.get_by_kind(MemoryKind.RUN, limit=1)
        assert "first run" in entries[0].metadata["delta_line"]

    def test_first_run_snapshot_excludes_memory_db(
        self, store: MemoryStore, state_with_manifest, tmp_path
    ):
        append_run_entry(store, state_with_manifest, "aaa111", root=tmp_path, timestamp=FIXED_TS)
        entries = store.get_by_kind(MemoryKind.RUN, limit=1)
        snapshot = entries[0].metadata["snapshot"]
        assert "memory.db" not in snapshot
        assert "research/report.md" in snapshot

    def test_first_run_forward_compat_slots_empty(
        self, store: MemoryStore, state_with_manifest, tmp_path
    ):
        append_run_entry(store, state_with_manifest, "aaa111", root=tmp_path, timestamp=FIXED_TS)
        entries = store.get_by_kind(MemoryKind.RUN, limit=1)
        meta = entries[0].metadata
        assert meta["decisions"] == []
        assert meta["gotchas"] == []

    def test_first_run_captures_step_statuses(
        self, store: MemoryStore, state_with_manifest, tmp_path
    ):
        append_run_entry(store, state_with_manifest, "aaa111", root=tmp_path, timestamp=FIXED_TS)
        entries = store.get_by_kind(MemoryKind.RUN, limit=1)
        steps = entries[0].metadata["steps"]
        assert "research" in steps
        assert "discipline" in steps


class TestSubsequentRun:
    def test_second_run_computes_delta(self, store: MemoryStore, state_with_manifest, tmp_path):
        # First run
        append_run_entry(store, state_with_manifest, "run001", root=tmp_path, timestamp=FIXED_TS)

        # Mutate manifest — change one checksum
        state_with_manifest.install_manifest[0] = InstallEntry(
            path="research/report.md",
            owner="research",
            kind="research",
            created_at=datetime.now(UTC),
            checksum="NEWCHECKSUM999",
        )

        ts2 = datetime(2026, 6, 8, 13, 0, 0, tzinfo=UTC)
        append_run_entry(store, state_with_manifest, "run002", root=tmp_path, timestamp=ts2)

        assert store.count(MemoryKind.RUN) == 2
        entries = store.get_by_kind(MemoryKind.RUN, limit=2)
        # Newest first — run002 is at index 0
        second_entry = entries[0]
        assert "research/report.md" in second_entry.metadata["artifacts_changed"]

    def test_second_run_delta_line_not_first_run(
        self, store: MemoryStore, state_with_manifest, tmp_path
    ):
        append_run_entry(store, state_with_manifest, "run001", root=tmp_path, timestamp=FIXED_TS)
        ts2 = datetime(2026, 6, 8, 13, 0, 0, tzinfo=UTC)
        append_run_entry(store, state_with_manifest, "run002", root=tmp_path, timestamp=ts2)
        entries = store.get_by_kind(MemoryKind.RUN, limit=2)
        assert entries[0].metadata["delta_line"] != "first run"


class TestIdempotency:
    def test_two_calls_same_run_id_leaves_one_entry(
        self, store: MemoryStore, state_with_manifest, tmp_path
    ):
        append_run_entry(store, state_with_manifest, "dup001", root=tmp_path, timestamp=FIXED_TS)
        append_run_entry(store, state_with_manifest, "dup001", root=tmp_path, timestamp=FIXED_TS)
        assert store.count(MemoryKind.RUN) == 1


class TestDryRun:
    def test_dry_run_entry_has_tag(self, store: MemoryStore, state_with_manifest, tmp_path):
        append_run_entry(
            store, state_with_manifest, "dry001", root=tmp_path, dry_run=True, timestamp=FIXED_TS
        )
        entries = store.get_by_kind(MemoryKind.RUN, limit=1)
        assert "dry_run" in entries[0].tags

    def test_dry_run_metadata_flag(self, store: MemoryStore, state_with_manifest, tmp_path):
        append_run_entry(
            store, state_with_manifest, "dry001", root=tmp_path, dry_run=True, timestamp=FIXED_TS
        )
        entries = store.get_by_kind(MemoryKind.RUN, limit=1)
        assert entries[0].metadata["dry_run"] is True

    def test_dry_run_runlog_notes_dry_run(self, store: MemoryStore, state_with_manifest, tmp_path):
        append_run_entry(
            store, state_with_manifest, "dry001", root=tmp_path, dry_run=True, timestamp=FIXED_TS
        )
        runlog = tmp_path / ".planning" / "RUNLOG.md"
        assert runlog.exists()
        content = runlog.read_text()
        assert "dry_run" in content


class TestRunlogMirror:
    def test_runlog_created_and_contains_run_id(
        self, store: MemoryStore, state_with_manifest, tmp_path
    ):
        append_run_entry(store, state_with_manifest, "log001", root=tmp_path, timestamp=FIXED_TS)
        runlog = tmp_path / ".planning" / "RUNLOG.md"
        assert runlog.exists()
        content = runlog.read_text()
        assert "log001" in content

    def test_runlog_contains_steps_and_delta(
        self, store: MemoryStore, state_with_manifest, tmp_path
    ):
        append_run_entry(store, state_with_manifest, "log001", root=tmp_path, timestamp=FIXED_TS)
        content = (tmp_path / ".planning" / "RUNLOG.md").read_text()
        assert "steps" in content
        assert "delta" in content

    def test_runlog_appends_newest_at_bottom(
        self, store: MemoryStore, state_with_manifest, tmp_path
    ):
        append_run_entry(store, state_with_manifest, "first00", root=tmp_path, timestamp=FIXED_TS)
        ts2 = datetime(2026, 6, 8, 13, 0, 0, tzinfo=UTC)
        append_run_entry(store, state_with_manifest, "second0", root=tmp_path, timestamp=ts2)
        content = (tmp_path / ".planning" / "RUNLOG.md").read_text()
        assert content.index("first00") < content.index("second0")


class TestNeverRaises:
    def test_runlog_write_failure_does_not_propagate(
        self, store: MemoryStore, state_with_manifest, tmp_path, monkeypatch
    ):
        """Even if RUNLOG.md cannot be written, memory entry still lands and no exception raised."""
        import builtins

        real_open = builtins.open

        def patched_open(file, mode="r", *args, **kwargs):
            if "RUNLOG.md" in str(file) and "a" in str(mode):
                raise OSError("disk full")
            return real_open(file, mode, *args, **kwargs)

        monkeypatch.setattr(builtins, "open", patched_open)

        # Must not raise
        append_run_entry(store, state_with_manifest, "safe001", root=tmp_path, timestamp=FIXED_TS)

        # Memory entry still landed
        assert store.count(MemoryKind.RUN) == 1

    def test_memory_add_failure_does_not_propagate(
        self, state_with_manifest, tmp_path, monkeypatch
    ):
        """If memory.add raises, append_run_entry must not propagate the exception."""
        from unittest.mock import MagicMock

        # Build a fake memory store whose count() returns 0 (not seen) but add() raises
        fake_memory = MagicMock(spec=MemoryStore)
        fake_memory.count.return_value = 0
        fake_memory.get_by_kind.return_value = []
        fake_memory.add.side_effect = RuntimeError("simulated storage failure")

        # Must not raise
        append_run_entry(
            fake_memory, state_with_manifest, "fail001", root=tmp_path, timestamp=FIXED_TS
        )

        # add() was attempted
        fake_memory.add.assert_called_once()


class TestRemovedPathDelta:
    def test_removed_path_appears_in_artifacts_changed(
        self, store: MemoryStore, state_with_manifest, tmp_path
    ):
        """A manifest entry present in run001 but absent in run002 is in artifacts_changed."""
        # run001 — both research/report.md and .planning/ROADMAP.md present
        append_run_entry(store, state_with_manifest, "run001", root=tmp_path, timestamp=FIXED_TS)

        # run002 — remove .planning/ROADMAP.md from manifest entirely
        state_with_manifest.install_manifest = [
            entry
            for entry in state_with_manifest.install_manifest
            if entry.path != ".planning/ROADMAP.md"
        ]

        ts2 = datetime(2026, 6, 8, 13, 0, 0, tzinfo=UTC)
        append_run_entry(store, state_with_manifest, "run002", root=tmp_path, timestamp=ts2)

        entries = store.get_by_kind(MemoryKind.RUN, limit=2)
        # Newest-first — run002 at index 0
        second_entry = entries[0]
        assert ".planning/ROADMAP.md" in second_entry.metadata["artifacts_changed"]
