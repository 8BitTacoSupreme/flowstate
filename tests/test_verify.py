"""Tests for flowstate.verify — VerifyResult + run_verify registry coverage."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from flowstate.state import FlowStateModel, InstallEntry
from flowstate.verify import run_verify

# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_state(
    tmp_path: Path,
    *,
    real_file: str | None = None,
    missing_file: str | None = None,
    empty_file: str | None = None,
    include_mutable: bool = False,
) -> FlowStateModel:
    """Build a FlowStateModel with install_manifest entries as requested."""
    state = FlowStateModel()
    entries: list[InstallEntry] = []

    if real_file:
        p = tmp_path / real_file
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("content")
        entries.append(
            InstallEntry(
                path=real_file,
                owner="test",
                kind="artifact",
                created_at=datetime.now(UTC),
                checksum="abc123",
            )
        )

    if missing_file:
        entries.append(
            InstallEntry(
                path=missing_file,
                owner="test",
                kind="artifact",
                created_at=datetime.now(UTC),
                checksum="abc123",
            )
        )

    if empty_file:
        p = tmp_path / empty_file
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"")
        entries.append(
            InstallEntry(
                path=empty_file,
                owner="test",
                kind="artifact",
                created_at=datetime.now(UTC),
                checksum="abc123",
            )
        )

    if include_mutable:
        entries.append(
            InstallEntry(
                path="memory.db",
                owner="memory",
                kind="memory",
                created_at=datetime.now(UTC),
                checksum=None,  # excluded from integrity check
            )
        )

    state.install_manifest = entries
    return state


def _write_fixture(fixtures_dir: Path, name: str, data: dict) -> Path:
    """Write a fixture JSON file into fixtures_dir; create dir if needed."""
    fixtures_dir.mkdir(parents=True, exist_ok=True)
    path = fixtures_dir / name
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _write_coverage_xml(root: Path, line_rate: float) -> None:
    """Write a minimal Cobertura-format coverage.xml with the given line-rate."""
    xml = f'<?xml version="1.0" ?>\n<coverage line-rate="{line_rate}" />\n'
    (root / "coverage.xml").write_text(xml, encoding="utf-8")


_COVERAGE_GATE = "Test coverage meets or exceeds 80% as required."
_MILESTONE_GATE = "Milestone satisfied: Ship v1.0"
_FORBIDDEN_ACTION = "Do not invent requirements not established in PROJECT.md."


# ── Artifact integrity tests ──────────────────────────────────────────────────


class TestArtifactIntegrity:
    def test_missing_artifact_produces_fail(self, tmp_path: Path):
        state = _make_state(tmp_path, missing_file="research/report.md")
        results = run_verify(state, tmp_path)
        fails = [r for r in results if r.status == "fail"]
        assert len(fails) == 1
        assert fails[0].gate == "produced-artifact-integrity"
        assert "research/report.md" in fails[0].message

    def test_empty_artifact_produces_fail(self, tmp_path: Path):
        state = _make_state(tmp_path, empty_file="research/report.md")
        results = run_verify(state, tmp_path)
        fails = [r for r in results if r.status == "fail"]
        assert len(fails) == 1
        assert "empty" in fails[0].message.lower()

    def test_present_nonempty_artifact_no_integrity_fail(self, tmp_path: Path):
        state = _make_state(tmp_path, real_file="research/report.md")
        results = run_verify(state, tmp_path)
        integrity_fails = [
            r for r in results if r.gate == "produced-artifact-integrity" and r.status == "fail"
        ]
        assert integrity_fails == []

    def test_checksum_none_memory_db_excluded(self, tmp_path: Path):
        """memory.db with checksum=None must not produce any integrity result."""
        state = _make_state(tmp_path, include_mutable=True)
        results = run_verify(state, tmp_path)
        integrity_results = [r for r in results if r.gate == "produced-artifact-integrity"]
        assert integrity_results == []

    def test_real_file_plus_mutable_no_fail(self, tmp_path: Path):
        """A present real artifact + a checksum=None entry → no integrity fail."""
        state = _make_state(tmp_path, real_file="flowstate.json", include_mutable=True)
        results = run_verify(state, tmp_path)
        fails = [r for r in results if r.status == "fail"]
        assert fails == []


# ── Coverage gate tests ───────────────────────────────────────────────────────


class TestCoverageGate:
    def test_coverage_pass_when_above_threshold(self, tmp_path: Path):
        state = FlowStateModel()
        fixtures_dir = tmp_path / ".planning" / "fixtures"
        _write_fixture(fixtures_dir, "starter.json", {"acceptance_gates": [_COVERAGE_GATE]})
        _write_coverage_xml(tmp_path, 0.92)
        results = run_verify(state, tmp_path)
        cov = [r for r in results if _COVERAGE_RE_GATE_TEXT in r.gate]
        assert len(cov) == 1
        assert cov[0].status == "pass"
        assert "92.0%" in cov[0].message

    def test_coverage_fail_when_below_threshold(self, tmp_path: Path):
        state = FlowStateModel()
        fixtures_dir = tmp_path / ".planning" / "fixtures"
        _write_fixture(fixtures_dir, "starter.json", {"acceptance_gates": [_COVERAGE_GATE]})
        _write_coverage_xml(tmp_path, 0.50)
        results = run_verify(state, tmp_path)
        cov = [r for r in results if _COVERAGE_RE_GATE_TEXT in r.gate]
        assert len(cov) == 1
        assert cov[0].status == "fail"
        assert "50.0%" in cov[0].message

    def test_coverage_skip_when_no_coverage_xml(self, tmp_path: Path):
        state = FlowStateModel()
        fixtures_dir = tmp_path / ".planning" / "fixtures"
        _write_fixture(fixtures_dir, "starter.json", {"acceptance_gates": [_COVERAGE_GATE]})
        # coverage.xml deliberately NOT written
        results = run_verify(state, tmp_path)
        cov = [r for r in results if _COVERAGE_RE_GATE_TEXT in r.gate]
        assert len(cov) == 1
        assert cov[0].status == "skip"
        assert "coverage report" in cov[0].message.lower()

    def test_coverage_skip_mentions_absent(self, tmp_path: Path):
        """Skip message should reference that coverage.xml is absent."""
        state = FlowStateModel()
        fixtures_dir = tmp_path / ".planning" / "fixtures"
        _write_fixture(fixtures_dir, "s.json", {"acceptance_gates": [_COVERAGE_GATE]})
        results = run_verify(state, tmp_path)
        skip = next(r for r in results if r.status == "skip" and "coverage" in r.gate.lower())
        assert "absent" in skip.message or "coverage report" in skip.message


# Helper for matching gate text — avoids re-importing private constant
_COVERAGE_RE_GATE_TEXT = "Test coverage meets or exceeds"


# ── NL gate / forbidden action SKIP tests ────────────────────────────────────


class TestNLGates:
    def test_milestone_gate_skipped(self, tmp_path: Path):
        state = FlowStateModel()
        fixtures_dir = tmp_path / ".planning" / "fixtures"
        _write_fixture(fixtures_dir, "starter.json", {"acceptance_gates": [_MILESTONE_GATE]})
        results = run_verify(state, tmp_path)
        assert len(results) == 1
        assert results[0].status == "skip"
        assert "not mechanically verifiable" in results[0].message

    def test_forbidden_action_skipped(self, tmp_path: Path):
        state = FlowStateModel()
        fixtures_dir = tmp_path / ".planning" / "fixtures"
        _write_fixture(fixtures_dir, "starter.json", {"forbidden_actions": [_FORBIDDEN_ACTION]})
        results = run_verify(state, tmp_path)
        assert len(results) == 1
        assert results[0].status == "skip"
        assert "forbidden action" in results[0].message

    def test_multiple_nl_gates_all_skipped(self, tmp_path: Path):
        state = FlowStateModel()
        fixtures_dir = tmp_path / ".planning" / "fixtures"
        gates = [_MILESTONE_GATE, "All described functionality works as specified."]
        forbidden = [_FORBIDDEN_ACTION, "Do not modify files outside the stated task scope."]
        _write_fixture(
            fixtures_dir,
            "starter.json",
            {"acceptance_gates": gates, "forbidden_actions": forbidden},
        )
        results = run_verify(state, tmp_path)
        # No integrity results (empty manifest) → all 4 should be skips from gates
        assert all(r.status == "skip" for r in results)
        assert len(results) == 4


# ── Malformed fixture tests ───────────────────────────────────────────────────


class TestMalformedFixture:
    def test_malformed_json_does_not_raise(self, tmp_path: Path):
        state = FlowStateModel()
        fixtures_dir = tmp_path / ".planning" / "fixtures"
        fixtures_dir.mkdir(parents=True)
        bad = fixtures_dir / "bad.json"
        bad.write_text("{bad json", encoding="utf-8")
        # Must not raise — this is the core constraint
        results = run_verify(state, tmp_path)
        assert isinstance(results, list)

    def test_malformed_fixture_produces_skip_result(self, tmp_path: Path):
        state = FlowStateModel()
        fixtures_dir = tmp_path / ".planning" / "fixtures"
        fixtures_dir.mkdir(parents=True)
        bad = fixtures_dir / "bad.json"
        bad.write_text("{bad json", encoding="utf-8")
        results = run_verify(state, tmp_path)
        skip_results = [r for r in results if r.status == "skip"]
        assert len(skip_results) >= 1
        assert any("malformed" in r.message.lower() for r in skip_results)

    def test_good_fixture_alongside_malformed_still_processed(self, tmp_path: Path):
        """A valid fixture in the same dir must still be evaluated."""
        state = FlowStateModel()
        fixtures_dir = tmp_path / ".planning" / "fixtures"
        fixtures_dir.mkdir(parents=True)
        (fixtures_dir / "bad.json").write_text("{broken", encoding="utf-8")
        _write_fixture(fixtures_dir, "good.json", {"forbidden_actions": [_FORBIDDEN_ACTION]})
        results = run_verify(state, tmp_path)
        # bad.json → 1 malformed-skip, good.json → 1 forbidden-action-skip
        assert len(results) == 2
        messages = {r.message for r in results}
        assert any("malformed" in m.lower() for m in messages)
        assert any("forbidden action" in m.lower() for m in messages)


# ── Empty / absent fixtures dir ───────────────────────────────────────────────


class TestEmptyFixturesDir:
    def test_no_fixtures_dir_does_not_raise(self, tmp_path: Path):
        state = FlowStateModel()
        # .planning/fixtures deliberately absent
        results = run_verify(state, tmp_path)
        assert isinstance(results, list)

    def test_empty_manifest_no_fixtures_returns_empty(self, tmp_path: Path):
        state = FlowStateModel()
        results = run_verify(state, tmp_path)
        assert results == []

    def test_empty_fixtures_dir_returns_only_integrity_backbone(self, tmp_path: Path):
        """An empty fixtures dir → only backbone integrity results (here: none since empty manifest)."""
        state = FlowStateModel()
        fixtures_dir = tmp_path / ".planning" / "fixtures"
        fixtures_dir.mkdir(parents=True)
        results = run_verify(state, tmp_path)
        assert results == []

    def test_missing_artifact_no_fixtures_dir_still_fails(self, tmp_path: Path):
        """Backbone runs even when fixtures dir is absent."""
        state = _make_state(tmp_path, missing_file="research/report.md")
        results = run_verify(state, tmp_path)
        fails = [r for r in results if r.status == "fail"]
        assert len(fails) == 1
        assert fails[0].gate == "produced-artifact-integrity"
