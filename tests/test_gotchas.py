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

    def test_replaces_iso_timestamp_z_suffix(self):
        """Z-suffix UTC timestamp is fully replaced with <ts> placeholder."""
        from flowstate.gotchas import _normalize

        result = _normalize("error at 2026-01-15T10:30:00Z in module")
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

    def test_z_and_offset_timestamp_same_sig(self):
        """Z-suffix and +00:00 offset timestamps on the same message produce the same sig."""
        from flowstate.gotchas import _signature

        sig1 = _signature("verifier", "failed at 2026-06-08T12:00:00Z")
        sig2 = _signature("verifier", "failed at 2026-06-08T12:00:00+00:00")
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


# ---------------------------------------------------------------------------
# _parse_frontmatter
# ---------------------------------------------------------------------------


class TestParseFrontmatter:
    def test_parses_simple_key_value(self):
        from flowstate.gotchas import _parse_frontmatter

        text = "---\nstatus: failed\nphase: 07\n---\nbody"
        result = _parse_frontmatter(text)
        assert result["status"] == "failed"
        assert result["phase"] == "07"

    def test_returns_empty_when_no_leading_dashes(self):
        from flowstate.gotchas import _parse_frontmatter

        result = _parse_frontmatter("# No frontmatter\n\ncontent here")
        assert result == {}

    def test_returns_empty_on_empty_string(self):
        from flowstate.gotchas import _parse_frontmatter

        assert _parse_frontmatter("") == {}

    def test_handles_leading_blank_lines(self):
        from flowstate.gotchas import _parse_frontmatter

        text = "\n\n---\nstatus: complete\n---\n"
        result = _parse_frontmatter(text)
        assert result["status"] == "complete"

    def test_value_with_colon(self):
        from flowstate.gotchas import _parse_frontmatter

        text = "---\nurl: http://example.com:8080/path\n---\n"
        result = _parse_frontmatter(text)
        # value is everything after first ':'
        assert result["url"] == "http://example.com:8080/path"

    def test_malformed_no_closing_dashes(self):
        from flowstate.gotchas import _parse_frontmatter

        # No closing --- — should still parse what it finds (or return partially)
        text = "---\nstatus: failed\n"
        result = _parse_frontmatter(text)
        # May return partially or empty — must not raise
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# harvest_planning_gotchas
# ---------------------------------------------------------------------------


class TestHarvestPlanningGotchas:
    def _make_phases(self, tmp_path: Path) -> Path:
        """Create .planning/phases/ directory structure."""
        phases = tmp_path / ".planning" / "phases"
        phases.mkdir(parents=True, exist_ok=True)
        return phases

    def test_verification_failed_status_captures_gotcha(self, store: MemoryStore, tmp_path: Path):
        """A VERIFICATION.md with status: failed yields >=1 gotcha tagged source='verifier'."""
        from flowstate.gotchas import harvest_planning_gotchas

        phases = self._make_phases(tmp_path)
        phase_dir = phases / "07-test"
        phase_dir.mkdir()
        (phase_dir / "07-VERIFICATION.md").write_text(
            "---\nstatus: failed\n---\n\n# Result\n\nFailed verification.\n"
        )

        harvest_planning_gotchas(store, tmp_path)

        entries = [e for e in store.get_by_kind(MemoryKind.INSIGHT, limit=50) if "gotcha" in e.tags]
        verifier_entries = [e for e in entries if "verifier" in e.tags]
        assert len(verifier_entries) >= 1

    def test_verification_with_gaps_section_captures_gotcha(
        self, store: MemoryStore, tmp_path: Path
    ):
        """A VERIFICATION.md with a gaps section captures gap items."""
        from flowstate.gotchas import harvest_planning_gotchas

        phases = self._make_phases(tmp_path)
        phase_dir = phases / "07-test"
        phase_dir.mkdir()
        (phase_dir / "07-VERIFICATION.md").write_text(
            "---\nstatus: blocked\n---\n\n## Gaps\n\n- Missing test for X\n- Y not implemented\n"
        )

        harvest_planning_gotchas(store, tmp_path)

        entries = [e for e in store.get_by_kind(MemoryKind.INSIGHT, limit=50) if "gotcha" in e.tags]
        verifier_entries = [e for e in entries if "verifier" in e.tags]
        assert len(verifier_entries) >= 1

    def test_review_blocker_captures_gotcha(self, store: MemoryStore, tmp_path: Path):
        """A REVIEW.md with BLOCKER findings yields gotchas tagged source='plan-checker'."""
        from flowstate.gotchas import harvest_planning_gotchas

        phases = self._make_phases(tmp_path)
        phase_dir = phases / "07-test"
        phase_dir.mkdir()
        (phase_dir / "07-REVIEW.md").write_text(
            "# Review\n\n## Findings\n\nBLOCKER: missing auth on endpoint\nHIGH: unvalidated input\n"
        )

        harvest_planning_gotchas(store, tmp_path)

        entries = [e for e in store.get_by_kind(MemoryKind.INSIGHT, limit=50) if "gotcha" in e.tags]
        checker_entries = [e for e in entries if "plan-checker" in e.tags]
        assert len(checker_entries) >= 1

    def test_review_medium_captures_warning_severity(self, store: MemoryStore, tmp_path: Path):
        """MEDIUM findings in REVIEW.md are captured with severity='warning'."""
        from flowstate.gotchas import harvest_planning_gotchas

        phases = self._make_phases(tmp_path)
        phase_dir = phases / "07-test"
        phase_dir.mkdir()
        (phase_dir / "07-REVIEW.md").write_text(
            "# Review\n\nMEDIUM: could improve error messages\n"
        )

        harvest_planning_gotchas(store, tmp_path)

        entries = [e for e in store.get_by_kind(MemoryKind.INSIGHT, limit=50) if "gotcha" in e.tags]
        checker_entries = [e for e in entries if "plan-checker" in e.tags]
        assert len(checker_entries) >= 1
        assert checker_entries[0].metadata.get("severity") == "warning"

    def test_no_phases_dir_returns_normally(self, store: MemoryStore, tmp_path: Path):
        """harvest_planning_gotchas on a root with no .planning/phases returns without error."""
        from flowstate.gotchas import harvest_planning_gotchas

        # No phases dir — must not raise
        harvest_planning_gotchas(store, tmp_path)
        # Nothing captured
        entries = [e for e in store.get_by_kind(MemoryKind.INSIGHT) if "gotcha" in e.tags]
        assert len(entries) == 0

    def test_malformed_verification_is_skipped(self, store: MemoryStore, tmp_path: Path):
        """A malformed/binary VERIFICATION.md is skipped without raising or hanging."""
        from flowstate.gotchas import harvest_planning_gotchas

        phases = self._make_phases(tmp_path)
        phase_dir = phases / "07-test"
        phase_dir.mkdir()
        # Write binary garbage
        (phase_dir / "07-VERIFICATION.md").write_bytes(b"\x00\xff\xfe" * 100)

        # Must not raise
        harvest_planning_gotchas(store, tmp_path)

    def test_double_harvest_deduplicates(self, store: MemoryStore, tmp_path: Path):
        """Running harvest twice over the same artifacts increments count, not duplicates."""
        from flowstate.gotchas import harvest_planning_gotchas

        phases = self._make_phases(tmp_path)
        phase_dir = phases / "07-test"
        phase_dir.mkdir()
        (phase_dir / "07-VERIFICATION.md").write_text(
            "---\nstatus: failed\n---\n\n# Result\n\nFailed.\n"
        )

        harvest_planning_gotchas(store, tmp_path)
        harvest_planning_gotchas(store, tmp_path)

        entries = [e for e in store.get_by_kind(MemoryKind.INSIGHT, limit=50) if "gotcha" in e.tags]
        # Should have deduplicated — same signature → count incremented, not duplicated
        # Total unique signatures should be <= entries before harvest
        verifier_entries = [e for e in entries if "verifier" in e.tags]
        # At least 1 verifier entry
        assert len(verifier_entries) >= 1
        # Count should be >= 2 for at least one entry (deduplicated across two runs)
        counts = [e.metadata.get("count", 1) for e in verifier_entries]
        assert any(c >= 2 for c in counts)
