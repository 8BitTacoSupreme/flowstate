"""Tests for flowstate.journal — append_run_entry behavior."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from flowstate.journal import append_run_entry, append_verify_entry
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


class TestConsumptionMetadata:
    def test_consumption_kwargs_written_to_metadata(
        self, store: MemoryStore, state_with_manifest, tmp_path
    ):
        append_run_entry(
            store,
            state_with_manifest,
            "con001",
            root=tmp_path,
            timestamp=FIXED_TS,
            tokens_in=1234,
            tokens_out=567,
            cache_read=89,
            wall_clock_s=4.25,
        )
        meta = store.get_by_kind(MemoryKind.RUN, limit=1)[0].metadata
        assert meta["tokens_in"] == 1234
        assert meta["tokens_out"] == 567
        assert meta["cache_read"] == 89
        assert meta["wall_clock_s"] == 4.25

    def test_consumption_defaults_zero_and_none(
        self, store: MemoryStore, state_with_manifest, tmp_path
    ):
        append_run_entry(store, state_with_manifest, "con002", root=tmp_path, timestamp=FIXED_TS)
        meta = store.get_by_kind(MemoryKind.RUN, limit=1)[0].metadata
        assert meta["tokens_in"] == 0
        assert meta["tokens_out"] == 0
        assert meta["cache_read"] == 0
        assert meta["wall_clock_s"] is None


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


class TestAppendVerifyEntry:
    """Tests for the append_verify_entry sibling (08-02 VER-02)."""

    def _make_results(self, tmp_path):
        """Build a mix of pass/fail/skip VerifyResult instances."""
        from flowstate.verify import VerifyResult

        return [
            VerifyResult(gate="artifact-exists", status="pass", message="ok", fixture="s.json"),
            VerifyResult(
                gate="coverage-gate", status="fail", message="below threshold", fixture="s.json"
            ),
            VerifyResult(
                gate="milestone-check", status="skip", message="not verifiable", fixture="s.json"
            ),
        ]

    def test_writes_one_run_entry_tagged_verify(self, store: MemoryStore, tmp_path):
        results = self._make_results(tmp_path)
        append_verify_entry(store, tmp_path, results)
        entries = store.get_by_kind(MemoryKind.RUN, limit=10)
        assert len(entries) == 1
        assert "verify" in entries[0].tags

    def test_metadata_counts_match_results(self, store: MemoryStore, tmp_path):
        results = self._make_results(tmp_path)
        append_verify_entry(store, tmp_path, results)
        meta = store.get_by_kind(MemoryKind.RUN, limit=1)[0].metadata
        assert meta["gates_passed"] == 1
        assert meta["gates_failed"] == 1
        assert meta["gates_skipped"] == 1

    def test_metadata_failed_signatures_contains_fail_gates(self, store: MemoryStore, tmp_path):
        results = self._make_results(tmp_path)
        append_verify_entry(store, tmp_path, results)
        meta = store.get_by_kind(MemoryKind.RUN, limit=1)[0].metadata
        assert meta["failed_signatures"] == ["coverage-gate"]

    def test_metadata_verify_flag_is_true(self, store: MemoryStore, tmp_path):
        results = self._make_results(tmp_path)
        append_verify_entry(store, tmp_path, results)
        meta = store.get_by_kind(MemoryKind.RUN, limit=1)[0].metadata
        assert meta["verify"] is True

    def test_runlog_created_and_contains_verify(self, store: MemoryStore, tmp_path):
        results = self._make_results(tmp_path)
        append_verify_entry(store, tmp_path, results)
        runlog = tmp_path / ".planning" / "RUNLOG.md"
        assert runlog.exists()
        content = runlog.read_text()
        assert "verify" in content

    def test_runlog_contains_count_line(self, store: MemoryStore, tmp_path):
        results = self._make_results(tmp_path)
        append_verify_entry(store, tmp_path, results)
        content = (tmp_path / ".planning" / "RUNLOG.md").read_text()
        assert "pass" in content
        assert "fail" in content
        assert "skip" in content

    def test_all_pass_no_failed_signatures(self, store: MemoryStore, tmp_path):
        from flowstate.verify import VerifyResult

        results = [
            VerifyResult(gate="gate-a", status="pass", message="ok", fixture="s.json"),
            VerifyResult(gate="gate-b", status="pass", message="ok", fixture="s.json"),
        ]
        append_verify_entry(store, tmp_path, results)
        meta = store.get_by_kind(MemoryKind.RUN, limit=1)[0].metadata
        assert meta["gates_failed"] == 0
        assert meta["failed_signatures"] == []

    def test_never_raises_when_memory_add_raises(self, tmp_path, monkeypatch):
        from unittest.mock import MagicMock

        from flowstate.verify import VerifyResult

        fake_memory = MagicMock(spec=MemoryStore)
        fake_memory.add.side_effect = RuntimeError("storage failure")

        results = [VerifyResult(gate="g", status="pass", message="ok", fixture="s.json")]
        # Must not raise
        append_verify_entry(fake_memory, tmp_path, results)
        fake_memory.add.assert_called_once()

    def test_never_raises_when_runlog_unwritable(self, store: MemoryStore, tmp_path, monkeypatch):
        import builtins

        from flowstate.verify import VerifyResult

        real_open = builtins.open

        def patched_open(file, mode="r", *args, **kwargs):
            if "RUNLOG.md" in str(file) and "a" in str(mode):
                raise OSError("disk full")
            return real_open(file, mode, *args, **kwargs)

        monkeypatch.setattr(builtins, "open", patched_open)

        results = [VerifyResult(gate="g", status="pass", message="ok", fixture="s.json")]
        # Must not raise; memory entry still lands
        append_verify_entry(store, tmp_path, results)
        assert store.count(MemoryKind.RUN) == 1

    def test_never_raises_on_malformed_result_object(self, tmp_path):
        """WR-03: a result object lacking .status/.gate must not cause append_verify_entry to raise."""
        from unittest.mock import MagicMock

        fake_memory = MagicMock(spec=MemoryStore)
        fake_memory.add.return_value = None

        # An object with no .status attribute at all
        malformed_result = object()
        # Must not raise
        append_verify_entry(fake_memory, tmp_path, [malformed_result])


class TestGotchasSlot:
    """Tests for the gotchas metadata slot and RUNLOG gotchas line (07-04 GOT-01)."""

    def test_gotchas_slot_empty_when_no_gotchas_this_run(
        self, store: MemoryStore, state_with_manifest, tmp_path
    ):
        """When no gotchas exist for this run_id, metadata['gotchas'] is []."""
        append_run_entry(store, state_with_manifest, "nogtch0", root=tmp_path, timestamp=FIXED_TS)
        entries = store.get_by_kind(MemoryKind.RUN, limit=1)
        assert entries[0].metadata["gotchas"] == []

    def test_gotchas_slot_populated_with_this_run_signatures(
        self, store: MemoryStore, state_with_manifest, tmp_path
    ):
        """When a gotcha with matching run_id exists, metadata['gotchas'] contains its signature."""
        from flowstate.gotchas import capture_gotcha

        run_id = "gtchrun1"
        # Capture a gotcha for this run
        capture_gotcha(
            store,
            source="executor",
            message="Tool 'research' failed: timeout",
            root=tmp_path,
            severity="error",
            run_id=run_id,
        )

        append_run_entry(store, state_with_manifest, run_id, root=tmp_path, timestamp=FIXED_TS)
        entries = store.get_by_kind(MemoryKind.RUN, limit=1)
        gotchas_meta = entries[0].metadata["gotchas"]
        assert len(gotchas_meta) == 1
        # Should contain a signature (16-char hex)
        sig = gotchas_meta[0]
        assert len(sig) == 16

    def test_gotchas_slot_excludes_other_runs(
        self, store: MemoryStore, state_with_manifest, tmp_path
    ):
        """Gotchas from a different run_id are NOT included in this run's metadata slot."""
        from flowstate.gotchas import capture_gotcha

        # Capture a gotcha for a different run
        capture_gotcha(
            store,
            source="executor",
            message="Tool 'gsd' failed: crash",
            root=tmp_path,
            severity="error",
            run_id="other-run",
        )

        this_run_id = "thisrun1"
        append_run_entry(store, state_with_manifest, this_run_id, root=tmp_path, timestamp=FIXED_TS)
        entries = store.get_by_kind(MemoryKind.RUN, limit=1)
        assert entries[0].metadata["gotchas"] == []

    def test_runlog_gotchas_line_none_when_empty(
        self, store: MemoryStore, state_with_manifest, tmp_path
    ):
        """RUNLOG.md gotchas line shows '(none this run)' when no gotchas captured for this run."""
        append_run_entry(store, state_with_manifest, "nogtch1", root=tmp_path, timestamp=FIXED_TS)
        content = (tmp_path / ".planning" / "RUNLOG.md").read_text()
        # The gotchas line specifically uses the new placeholder (not the old one)
        assert "- gotchas: (none this run)" in content
        assert "- gotchas: (none this phase)" not in content

    def test_runlog_gotchas_line_shows_signatures_when_present(
        self, store: MemoryStore, state_with_manifest, tmp_path
    ):
        """RUNLOG.md gotchas line lists captured signatures joined by ', '."""
        from flowstate.gotchas import capture_gotcha

        run_id = "sigrun01"
        capture_gotcha(
            store,
            source="executor",
            message="Tool 'strategy' failed: auth error",
            root=tmp_path,
            severity="error",
            run_id=run_id,
        )

        append_run_entry(store, state_with_manifest, run_id, root=tmp_path, timestamp=FIXED_TS)
        content = (tmp_path / ".planning" / "RUNLOG.md").read_text()
        # Should NOT show the old placeholder on the gotchas line
        assert "- gotchas: (none this phase)" not in content
        assert "- gotchas: (none this run)" not in content
        # Extract the gotchas line and verify it has a signature value
        for line in content.splitlines():
            if line.startswith("- gotchas:"):
                value = line.split(":", 1)[1].strip()
                assert len(value) == 16, f"expected 16-char hex signature, got: {value!r}"
                break
