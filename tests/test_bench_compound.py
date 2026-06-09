"""Tests for the bench/ intrinsic compounding harness.

Covers (built incrementally across the Phase A tasks):
  - metric-core: each axis fires on a compounding sequence, detects regression
    on a worsening sequence, K=1 insufficient-data, never-raises on empty/short.
  - capture: _LAYER_HEADINGS coupling to context_prefix.py, never-raises reads,
    scaffold idempotency, gotcha attribution.
  - runner/report: caveat present, table+panel render, judge-stub refusal.
  - e2e: cheap-seed 3-iteration axes fire, cheap-dry smoke, JSON determinism.
"""

from __future__ import annotations

from pathlib import Path

from bench.metrics import (
    RunSnapshot,
    Scorecard,
    axis_convergence,
    axis_enrichment,
    axis_gotcha_learning,
    axis_verify_non_regression,
    compute_scorecard,
)

# ── Metric-core helpers ─────────────────────────────────────────────────────


def _snap(
    i: int,
    *,
    artifacts_changed: int = 0,
    new_gotchas: int = 0,
    reencountered_gotchas: int = 0,
    verify_pass: int = 0,
    verify_fail: int = 0,
    verify_skip: int = 0,
    prefix_tokens: int = 0,
    mem_hits: int = 0,
    layers_present: tuple[str, ...] = (),
) -> RunSnapshot:
    return RunSnapshot(
        run_index=i,
        run_id=f"run{i}",
        artifacts_changed=artifacts_changed,
        new_gotchas=new_gotchas,
        reencountered_gotchas=reencountered_gotchas,
        verify_pass=verify_pass,
        verify_fail=verify_fail,
        verify_skip=verify_skip,
        prefix_tokens=prefix_tokens,
        mem_hits=mem_hits,
        layers_present=layers_present,
    )


def _compounding_sequence() -> list[RunSnapshot]:
    """A hand-built sequence where every axis registers compounding."""
    return [
        _snap(
            0,
            artifacts_changed=8,
            new_gotchas=4,
            reencountered_gotchas=0,
            verify_pass=2,
            verify_fail=2,
            prefix_tokens=100,
            mem_hits=1,
            layers_present=("## Eval Fixtures",),
        ),
        _snap(
            1,
            artifacts_changed=5,
            new_gotchas=2,
            reencountered_gotchas=2,
            verify_pass=3,
            verify_fail=1,
            prefix_tokens=200,
            mem_hits=3,
            layers_present=("## Eval Fixtures", "## Gotchas"),
        ),
        _snap(
            2,
            artifacts_changed=2,
            new_gotchas=0,
            reencountered_gotchas=3,
            verify_pass=4,
            verify_fail=0,
            prefix_tokens=350,
            mem_hits=6,
            layers_present=("## Eval Fixtures", "## Gotchas", "## Prior Knowledge"),
        ),
    ]


def _regressing_sequence() -> list[RunSnapshot]:
    """A hand-built sequence where every axis registers regression."""
    return [
        _snap(
            0,
            artifacts_changed=2,
            new_gotchas=0,
            reencountered_gotchas=3,
            verify_pass=4,
            verify_fail=0,
            prefix_tokens=350,
            mem_hits=6,
            layers_present=("## Eval Fixtures", "## Gotchas", "## Prior Knowledge"),
        ),
        _snap(
            1,
            artifacts_changed=5,
            new_gotchas=2,
            reencountered_gotchas=2,
            verify_pass=3,
            verify_fail=1,
            prefix_tokens=200,
            mem_hits=3,
            layers_present=("## Eval Fixtures", "## Gotchas"),
        ),
        _snap(
            2,
            artifacts_changed=8,
            new_gotchas=4,
            reencountered_gotchas=0,
            verify_pass=2,
            verify_fail=2,
            prefix_tokens=100,
            mem_hits=1,
            layers_present=("## Eval Fixtures",),
        ),
    ]


# ── Axis unit tests ─────────────────────────────────────────────────────────


def test_axis_convergence_fires_on_decreasing_deltas():
    assert axis_convergence(_compounding_sequence()) == "compounding"


def test_axis_convergence_detects_regression_on_rising_deltas():
    assert axis_convergence(_regressing_sequence()) == "regressing"


def test_axis_gotcha_learning_fires_when_new_decays():
    assert axis_gotcha_learning(_compounding_sequence()) == "compounding"


def test_axis_gotcha_learning_detects_regression_when_new_rises():
    assert axis_gotcha_learning(_regressing_sequence()) == "regressing"


def test_axis_verify_non_regression_fires_when_improving():
    assert axis_verify_non_regression(_compounding_sequence()) == "compounding"


def test_axis_verify_non_regression_detects_regression():
    assert axis_verify_non_regression(_regressing_sequence()) == "regressing"


def test_axis_enrichment_fires_when_prefix_grows():
    assert axis_enrichment(_compounding_sequence()) == "compounding"


def test_axis_enrichment_detects_regression_when_prefix_shrinks():
    assert axis_enrichment(_regressing_sequence()) == "regressing"


def test_flat_sequence_yields_flat_on_every_axis():
    flat = [
        _snap(0, artifacts_changed=4, new_gotchas=1, verify_pass=3, prefix_tokens=200, mem_hits=2),
        _snap(1, artifacts_changed=4, new_gotchas=1, verify_pass=3, prefix_tokens=200, mem_hits=2),
    ]
    assert axis_convergence(flat) == "flat"
    assert axis_gotcha_learning(flat) == "flat"
    assert axis_verify_non_regression(flat) == "flat"
    assert axis_enrichment(flat) == "flat"


# ── Scorecard tests ─────────────────────────────────────────────────────────


def test_compute_scorecard_compounding_verdict():
    card = compute_scorecard(_compounding_sequence())
    assert isinstance(card, Scorecard)
    assert card.compounding_score >= 2
    assert card.axis_enrichment == "compounding"
    assert "regressing" not in (
        card.axis_convergence,
        card.axis_gotcha_learning,
        card.axis_verify_non_regression,
        card.axis_enrichment,
    )
    assert card.verdict == "compounding"


def test_compute_scorecard_score_clamped_and_in_range():
    card = compute_scorecard(_regressing_sequence())
    assert -4 <= card.compounding_score <= 4
    assert card.verdict != "compounding"


def test_k1_yields_all_flat_insufficient_data_and_score_zero():
    card = compute_scorecard([_snap(0, artifacts_changed=3, prefix_tokens=100)])
    assert card.axis_convergence == "flat"
    assert card.axis_gotcha_learning == "flat"
    assert card.axis_verify_non_regression == "flat"
    assert card.axis_enrichment == "flat"
    assert card.compounding_score == 0
    assert card.verdict != "compounding"


def test_compute_scorecard_never_raises_on_empty_and_single():
    # empty list
    card_empty = compute_scorecard([])
    assert card_empty.compounding_score == 0
    assert card_empty.verdict != "compounding"
    # single snapshot
    card_single = compute_scorecard([_snap(0)])
    assert card_single.compounding_score == 0


def test_axes_never_raise_on_empty_input():
    for fn in (
        axis_convergence,
        axis_gotcha_learning,
        axis_verify_non_regression,
        axis_enrichment,
    ):
        assert fn([]) == "flat"
        assert fn([_snap(0)]) == "flat"


def test_verdict_requires_enrichment_compounding():
    """Score >= 2 but enrichment flat must NOT yield a compounding verdict."""
    seq = [
        _snap(
            0,
            artifacts_changed=8,
            new_gotchas=4,
            verify_pass=2,
            verify_fail=2,
            prefix_tokens=200,
            mem_hits=3,
        ),
        _snap(
            1,
            artifacts_changed=2,
            new_gotchas=0,
            reencountered_gotchas=3,
            verify_pass=4,
            verify_fail=0,
            prefix_tokens=200,
            mem_hits=3,
        ),
    ]
    card = compute_scorecard(seq)
    assert card.axis_enrichment == "flat"
    assert card.verdict != "compounding"


_FIXTURE_ROOT = Path(__file__).resolve().parent.parent / "bench" / "fixtures" / "sample_project"


# ── Task 2: capture + project ───────────────────────────────────────────────


def test_layer_headings_match_context_prefix_source():
    """_LAYER_HEADINGS must match the actual headings emitted by context_prefix.py.

    Fails loudly if any heading drifts in the source module.
    """
    from bench.capture import _LAYER_HEADINGS

    flowstate_dir = Path(__file__).resolve().parent.parent / "flowstate"
    # "## Prior Knowledge" is emitted by MemoryStore.get_context (memory.py),
    # the other three by context_prefix.py. Scan the union of the emitters so
    # the guard couples to wherever each heading actually originates.
    src = (
        (flowstate_dir / "context_prefix.py").read_text()
        + "\n"
        + (flowstate_dir / "memory.py").read_text()
    )
    expected = (
        "## Eval Fixtures",
        "## Gotchas",
        "## Prior Knowledge",
        "## Since Last Run",
    )
    assert expected == _LAYER_HEADINGS
    for heading in _LAYER_HEADINGS:
        assert heading in src, f"layer heading drifted from its emitter: {heading!r}"


def test_capture_run_snapshot_never_raises_on_empty_dir(tmp_path: Path):
    from bench.capture import capture_run_snapshot
    from bench.metrics import RunSnapshot

    snap = capture_run_snapshot(tmp_path, "anything")
    assert isinstance(snap, RunSnapshot)
    assert snap.run_index == 0
    # Empty dir degrades to zeros / empty layers.
    assert snap.artifacts_changed == 0
    assert snap.layers_present == ()


def test_capture_run_index_derives_from_prior(tmp_path: Path):
    from bench.capture import capture_run_snapshot

    first = capture_run_snapshot(tmp_path, "q")
    second = capture_run_snapshot(tmp_path, "q", prior=first)
    assert second.run_index == first.run_index + 1


def test_scaffold_is_idempotent(tmp_path: Path):
    from bench.project import scaffold

    scaffold(tmp_path)
    fixture = tmp_path / ".planning" / "fixtures" / "starter.json"
    state = tmp_path / "flowstate.json"
    verification = tmp_path / ".planning" / "phases" / "01-foundation" / "01-VERIFICATION.md"
    assert fixture.exists()
    assert state.exists()
    assert verification.exists()
    first_fixture = fixture.read_text()
    first_verification = verification.read_text()

    scaffold(tmp_path)  # second run
    assert fixture.read_text() == first_fixture
    assert verification.read_text() == first_verification


def test_scaffold_verification_has_gaps_section(tmp_path: Path):
    from bench.project import scaffold

    scaffold(tmp_path)
    verification = (
        tmp_path / ".planning" / "phases" / "01-foundation" / "01-VERIFICATION.md"
    ).read_text()
    assert "Gaps" in verification
    # harvest_planning_gotchas should find bullets to capture.
    assert "- " in verification


def test_scaffold_verification_feeds_harvest(tmp_path: Path):
    """The scaffolded VERIFICATION.md must produce gotchas via harvest_planning_gotchas."""
    from bench.project import scaffold
    from flowstate.gotchas import harvest_planning_gotchas
    from flowstate.memory import MemoryStore

    scaffold(tmp_path)
    store = MemoryStore(root=tmp_path)
    try:
        harvest_planning_gotchas(store, tmp_path)
        assert len(store.get_gotchas()) >= 1
    finally:
        store.close()


def test_mutate_for_run_is_deterministic(tmp_path: Path):
    from bench.project import mutate_for_run, scaffold

    scaffold(tmp_path)
    mutate_for_run(tmp_path, 1)
    snapshot_a = (
        tmp_path / ".planning" / "phases" / "01-foundation" / "01-VERIFICATION.md"
    ).read_text()

    # Re-scaffold + same mutation index yields identical content.
    scaffold(tmp_path)
    mutate_for_run(tmp_path, 1)
    snapshot_b = (
        tmp_path / ".planning" / "phases" / "01-foundation" / "01-VERIFICATION.md"
    ).read_text()
    assert snapshot_a == snapshot_b


def test_mutate_for_run_resolves_gaps_over_runs(tmp_path: Path):
    """Successive run indices remove gaps (gotcha gaps resolve over runs)."""
    from bench.project import mutate_for_run, scaffold

    scaffold(tmp_path)
    vpath = tmp_path / ".planning" / "phases" / "01-foundation" / "01-VERIFICATION.md"

    def _gap_count() -> int:
        return vpath.read_text().count("\n- ")

    mutate_for_run(tmp_path, 0)
    early = _gap_count()
    mutate_for_run(tmp_path, 2)
    late = _gap_count()
    assert late < early


def test_capture_attributes_new_gotchas_by_run_id(tmp_path: Path):
    """A gotcha stamped with the current run_id counts as new this run."""
    from datetime import UTC, datetime

    from bench.capture import capture_run_snapshot
    from flowstate.gotchas import capture_gotcha
    from flowstate.memory import MemoryStore

    store = MemoryStore(root=tmp_path)
    try:
        capture_gotcha(
            store,
            source="verifier",
            message="boom in foo.py",
            root=tmp_path,
            run_id="run0",
            timestamp=datetime.now(UTC),
        )
    finally:
        store.close()

    snap = capture_run_snapshot(tmp_path, "boom", run_id="run0")
    assert snap.new_gotchas >= 1
