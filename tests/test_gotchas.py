"""Tests for flowstate.gotchas — signature normalization, dedup/upsert, GOTCHAS.md mirror."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from flowstate.memory import MemoryEntry, MemoryKind, MemoryStore


@pytest.fixture()
def store(tmp_path: Path) -> MemoryStore:
    with MemoryStore(root=tmp_path) as s:
        yield s


# ---------------------------------------------------------------------------
# Signature and normalization
# ---------------------------------------------------------------------------


class TestNormalize:
    def test_lowercases(self):
        from flowstate.gotchas import _normalize

        assert _normalize("UPPER CASE") == "upper case"

    def test_collapses_whitespace(self):
        from flowstate.gotchas import _normalize

        assert _normalize("  hello   world  ") == "hello world"

    def test_replaces_absolute_path_with_basename(self):
        from flowstate.gotchas import _normalize

        result = _normalize("failed to open /usr/local/lib/python3.12/site.py")
        assert "/usr/local/lib/python3.12" not in result
        assert "site.py" in result

    def test_replaces_iso_timestamp(self):
        from flowstate.gotchas import _normalize

        result = _normalize("error at 2026-01-15T10:30:00+00:00 in module")
        assert "2026-01-15" not in result
        assert "<ts>" in result

    def test_replaces_12hex_run_id(self):
        from flowstate.gotchas import _normalize

        result = _normalize("run abc123def456 failed")
        assert "abc123def456" not in result
        assert "<id>" in result

    def test_replaces_digit_runs(self):
        from flowstate.gotchas import _normalize

        result = _normalize("line 42 failed with code 500")
        assert "42" not in result
        assert "500" not in result
        assert "<n>" in result

    def test_path_replaced_before_digits(self):
        """Path with digits in name should become basename, not <n>/<n>/<n>."""
        from flowstate.gotchas import _normalize

        result = _normalize("error in /tmp/phase07/abc123def456/run.py")
        # basename should survive (or at least the filename)
        assert "/tmp/phase07" not in result


class TestSignature:
    def test_same_source_message_same_sig(self):
        from flowstate.gotchas import _signature

        assert _signature("doctor", "tool failed") == _signature("doctor", "tool failed")

    def test_different_source_different_sig(self):
        from flowstate.gotchas import _signature

        assert _signature("doctor", "tool failed") != _signature("verifier", "tool failed")

    def test_path_variance_same_sig(self):
        """Two messages differing only by absolute path share the same signature."""
        from flowstate.gotchas import _signature

        sig1 = _signature("doctor", "failed to read /home/user/project/flowstate/memory.py")
        sig2 = _signature("doctor", "failed to read /opt/venv/lib/python3.12/flowstate/memory.py")
        assert sig1 == sig2

    def test_line_number_variance_same_sig(self):
        """Two messages differing only by line number share the same signature."""
        from flowstate.gotchas import _signature

        sig1 = _signature("doctor", "SyntaxError at line 42 in module")
        sig2 = _signature("doctor", "SyntaxError at line 99 in module")
        assert sig1 == sig2

    def test_iso_timestamp_variance_same_sig(self):
        """Two messages differing only by ISO timestamp share the same signature."""
        from flowstate.gotchas import _signature

        sig1 = _signature("verifier", "status failed at 2026-01-01T00:00:00+00:00")
        sig2 = _signature("verifier", "status failed at 2026-06-15T12:34:56+00:00")
        assert sig1 == sig2

    def test_run_id_variance_same_sig(self):
        """Two messages differing only by 12-hex run_id share the same signature."""
        from flowstate.gotchas import _signature

        sig1 = _signature("executor", "run abc123def456 failed")
        sig2 = _signature("executor", "run ffffff000000 failed")
        assert sig1 == sig2

    def test_sig_length_16(self):
        from flowstate.gotchas import _signature

        assert len(_signature("src", "msg")) == 16

    def test_sig_is_hex(self):
        from flowstate.gotchas import _signature

        sig = _signature("src", "msg")
        int(sig, 16)  # should not raise


# ---------------------------------------------------------------------------
# capture_gotcha — dedup/upsert
# ---------------------------------------------------------------------------


class TestCaptureGotcha:
    def test_first_capture_creates_insight_entry(self, store: MemoryStore, tmp_path: Path):
        from flowstate.gotchas import capture_gotcha

        capture_gotcha(store, source="doctor", message="X failed", root=tmp_path)

        entries = store.get_by_kind(MemoryKind.INSIGHT, limit=10)
        gotchas = [e for e in entries if "gotcha" in e.tags]
        assert len(gotchas) == 1
        assert gotchas[0].metadata["count"] == 1
        assert gotchas[0].metadata["first_seen"] == gotchas[0].metadata["last_seen"]

    def test_first_capture_tags(self, store: MemoryStore, tmp_path: Path):
        from flowstate.gotchas import capture_gotcha

        capture_gotcha(store, source="doctor", message="Y failed", root=tmp_path)
        entries = [e for e in store.get_by_kind(MemoryKind.INSIGHT) if "gotcha" in e.tags]
        assert len(entries) == 1
        assert "gotcha" in entries[0].tags
        assert "doctor" in entries[0].tags

    def test_second_capture_increments_count(self, store: MemoryStore, tmp_path: Path):
        """Two captures with same source+message → one entry with count=2."""
        from flowstate.gotchas import capture_gotcha

        ts1 = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
        ts2 = datetime(2026, 1, 2, 0, 0, 0, tzinfo=UTC)

        capture_gotcha(store, source="doctor", message="Z failed", root=tmp_path, timestamp=ts1)
        capture_gotcha(store, source="doctor", message="Z failed", root=tmp_path, timestamp=ts2)

        entries = [e for e in store.get_by_kind(MemoryKind.INSIGHT, limit=10) if "gotcha" in e.tags]
        assert len(entries) == 1
        assert entries[0].metadata["count"] == 2

    def test_second_capture_updates_last_seen(self, store: MemoryStore, tmp_path: Path):
        """Re-encounter advances last_seen; first_seen stays the same."""
        from flowstate.gotchas import capture_gotcha

        ts1 = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
        ts2 = datetime(2026, 1, 2, 0, 0, 0, tzinfo=UTC)

        capture_gotcha(store, source="doctor", message="W failed", root=tmp_path, timestamp=ts1)
        capture_gotcha(store, source="doctor", message="W failed", root=tmp_path, timestamp=ts2)

        entries = [e for e in store.get_by_kind(MemoryKind.INSIGHT, limit=10) if "gotcha" in e.tags]
        assert len(entries) == 1
        assert entries[0].metadata["first_seen"] == ts1.isoformat()
        assert entries[0].metadata["last_seen"] == ts2.isoformat()

    def test_path_variance_deduplicates(self, store: MemoryStore, tmp_path: Path):
        """Messages differing only by path collapse to one entry."""
        from flowstate.gotchas import capture_gotcha

        capture_gotcha(
            store,
            source="doctor",
            message="failed to read /home/alice/project/memory.py",
            root=tmp_path,
        )
        capture_gotcha(
            store,
            source="doctor",
            message="failed to read /opt/venv/lib/python3.12/memory.py",
            root=tmp_path,
        )

        entries = [e for e in store.get_by_kind(MemoryKind.INSIGHT, limit=10) if "gotcha" in e.tags]
        assert len(entries) == 1
        assert entries[0].metadata["count"] == 2

    def test_different_source_does_not_dedup(self, store: MemoryStore, tmp_path: Path):
        """Same message but different source → two distinct entries."""
        from flowstate.gotchas import capture_gotcha

        capture_gotcha(store, source="doctor", message="tool failed", root=tmp_path)
        capture_gotcha(store, source="verifier", message="tool failed", root=tmp_path)

        entries = [e for e in store.get_by_kind(MemoryKind.INSIGHT, limit=10) if "gotcha" in e.tags]
        assert len(entries) == 2

    def test_gotchas_md_written(self, store: MemoryStore, tmp_path: Path):
        """After capture, .planning/GOTCHAS.md exists and contains gotcha info."""
        from flowstate.gotchas import capture_gotcha

        capture_gotcha(store, source="doctor", message="tool failed", root=tmp_path)

        gotchas_md = tmp_path / ".planning" / "GOTCHAS.md"
        assert gotchas_md.exists()
        content = gotchas_md.read_text()
        assert "doctor" in content


# ---------------------------------------------------------------------------
# never-raises contract
# ---------------------------------------------------------------------------


class TestNeverRaises:
    def test_add_failure_does_not_propagate(self, tmp_path: Path):
        """capture_gotcha swallows storage errors and returns normally."""
        from flowstate.gotchas import capture_gotcha

        fake_memory = MagicMock(spec=MemoryStore)
        fake_memory.get_by_kind.return_value = []
        fake_memory.add.side_effect = RuntimeError("simulated storage failure")

        # Must not raise
        capture_gotcha(fake_memory, source="doctor", message="test", root=tmp_path)

    def test_update_failure_does_not_propagate(self, tmp_path: Path):
        """capture_gotcha swallows update errors and returns normally."""
        from flowstate.gotchas import capture_gotcha
        from flowstate.memory import MemoryKind

        ts = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
        sig = "abcd1234abcd5678"
        existing = MemoryEntry(
            id="abc000000001",
            kind=MemoryKind.INSIGHT,
            content="msg",
            summary="[doctor] msg",
            source="doctor",
            tags=["gotcha", "doctor"],
            metadata={
                "signature": sig,
                "source": "doctor",
                "severity": "warning",
                "first_seen": ts.isoformat(),
                "last_seen": ts.isoformat(),
                "count": 1,
            },
            created_at=ts,
        )

        fake_memory = MagicMock(spec=MemoryStore)
        fake_memory.get_by_kind.return_value = [existing]
        fake_memory.update.side_effect = RuntimeError("simulated update failure")

        # Must not raise
        capture_gotcha(
            fake_memory,
            source="doctor",
            message="msg",
            root=tmp_path,
            timestamp=datetime(2026, 1, 2, 0, 0, 0, tzinfo=UTC),
        )
