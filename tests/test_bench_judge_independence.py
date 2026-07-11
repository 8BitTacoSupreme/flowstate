"""Evaluator-independence caller tests (Phase 20 Wave 2).

Two concerns:
  1. The shared `_validate_judges` guard (built in 20-01) is enforced at the REAL
     judged-run chokepoint — `bench.compound_eval.main` — BEFORE any judging/bridge
     check, aborting fail-loud on an absent-or-same judge config (IND-01/D-06).
  2. IND-03: `bench.metrics.compute_scorecard` / `compounding_score` stays the
     authoritative deterministic scorer and the LLM judge (single- OR multi-judge)
     is EXCLUDED from it.

No test here makes a real subprocess/LLM call: the bridge is monkeypatched off and
RunSnapshot/JudgeResult objects are constructed directly.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import bench.compound_eval as ce
from bench.judge import JudgeResult, _validate_judges, aggregate_judges
from bench.metrics import RunSnapshot, compute_scorecard
from bench.report import write_json

# ── Task 1: the shared guard, called directly (unit) ─────────────────────────


def test_validate_judges_raises_on_same_model():
    """A judge equal to the producer is a hard fail (D-04/D-07)."""
    with pytest.raises(ValueError):
        _validate_judges(["opus"], "opus")


def test_validate_judges_raises_on_empty_set():
    """An absent judge model (empty list) is a hard stop — the empty-set branch fires
    BEFORE any judge==producer==None equality comparison (D-04)."""
    with pytest.raises(ValueError):
        _validate_judges([], None)  # type: ignore[arg-type]


def test_validate_judges_passes_on_distinct_pair():
    """A distinct judge/producer pair validates cleanly (no raise)."""
    assert _validate_judges(["opus"], "sonnet") is None


# ── Task 1: the guard on the REAL compound_eval path (not monkeypatched) ─────


def test_compound_eval_real_judge_without_model_aborts_config(tmp_path: Path, monkeypatch):
    """REAL path: --judge --allow-llm with NO --judge-model aborts with the judge-config
    exit code BEFORE the bridge check (absent judge model = empty set = hard stop).

    default --layers full => no producer gate, so the guard is the first thing to fire.
    The bridge is forced off to prove no real judging/subprocess runs (it never reaches
    it — the guard returns first)."""
    monkeypatch.setattr(ce, "_bridge_available", lambda: False)
    rc = ce.main(
        ["--mode", "real", "--judge", "--allow-llm", "--layers", "full", "--root", str(tmp_path)]
    )
    assert rc == ce._EXIT_JUDGE_CONFIG


def test_compound_eval_real_judge_equal_producer_aborts_config(tmp_path: Path, monkeypatch):
    """REAL path: judge model == producer model aborts with the judge-config exit code
    before any judge_run."""
    monkeypatch.setattr(ce, "_bridge_available", lambda: False)
    rc = ce.main(
        [
            "--mode",
            "real",
            "--judge",
            "--allow-llm",
            "--layers",
            "full",
            "--judge-model",
            "opus",
            "--producer-model",
            "opus",
            "--root",
            str(tmp_path),
        ]
    )
    assert rc == ce._EXIT_JUDGE_CONFIG


def test_compound_eval_real_distinct_pair_passes_guard(tmp_path: Path, monkeypatch):
    """REAL path: a DISTINCT judge/producer pair passes the guard and proceeds into
    _real_loop, which (no bridge in CI) returns _EXIT_NO_BRIDGE — proving the guard was
    passed, not the judge-config gate."""
    monkeypatch.setattr(ce, "_bridge_available", lambda: False)
    rc = ce.main(
        [
            "--mode",
            "real",
            "--judge",
            "--allow-llm",
            "--layers",
            "full",
            "--judge-model",
            "opus",
            "--producer-model",
            "sonnet",
            "--root",
            str(tmp_path),
        ]
    )
    assert rc != ce._EXIT_JUDGE_CONFIG
    assert rc == ce._EXIT_NO_BRIDGE


def test_compound_eval_parser_exposes_producer_model():
    """compound_eval owns a --producer-model arg (default None)."""
    args = ce._build_parser().parse_args(["--root", "x"])
    assert args.producer_model is None


# ── Task 1: the replicate conduit threads a DISTINCT pair ────────────────────


def test_replicate_run_trial_threads_distinct_models(monkeypatch, tmp_path):
    """_run_trial's compound_eval subprocess cmd carries explicit, DISTINCT
    --judge-model / --producer-model so the guard passes and the default real path
    stays runnable. Captured via a fake subprocess.run — no real subprocess."""
    import bench.replicate as rep

    captured: dict[str, list[str]] = {}

    def fake_run(cmd, check=False):
        captured["cmd"] = cmd
        # write a well-formed judge payload so _run_trial returns cleanly
        out_idx = cmd.index("--out") + 1
        Path(cmd[out_idx]).write_text('{"judge": {"per_run": [{"score": 8}]}}')

        class _P:
            returncode = 0

        return _P()

    monkeypatch.setattr(rep.subprocess, "run", fake_run)
    rep._run_trial("full", 1, tmp_path, "full0")

    cmd = captured["cmd"]
    assert "--judge-model" in cmd and "--producer-model" in cmd
    j = cmd[cmd.index("--judge-model") + 1]
    p = cmd[cmd.index("--producer-model") + 1]
    assert j and p and j != p


# ── Task 2: IND-03 — compounding_score is deterministic; the judge is EXCLUDED ─


def _snap(i: int, *, artifacts_changed: int, new_gotchas: int, prefix_tokens: int) -> RunSnapshot:
    """A RunSnapshot with the axis-driving fields set; the rest defaulted."""
    return RunSnapshot(
        run_index=i,
        run_id=f"run{i}",
        artifacts_changed=artifacts_changed,
        new_gotchas=new_gotchas,
        reencountered_gotchas=0,
        verify_pass=0,
        verify_fail=0,
        verify_skip=0,
        prefix_tokens=prefix_tokens,
        mem_hits=i,
        layers_present=("memory",) if i else (),
    )


def _fixed_snapshots() -> list[RunSnapshot]:
    """A hand-built converging sequence (deterministic, judge-independent)."""
    return [
        _snap(0, artifacts_changed=10, new_gotchas=5, prefix_tokens=100),
        _snap(1, artifacts_changed=6, new_gotchas=3, prefix_tokens=300),
        _snap(2, artifacts_changed=2, new_gotchas=1, prefix_tokens=800),
    ]


def test_compute_scorecard_is_deterministic_from_snapshots():
    """compute_scorecard's result (compounding_score + axis verdicts) is identical
    across calls for a fixed RunSnapshot list — no judge input, no hidden state."""
    snaps = _fixed_snapshots()
    a = compute_scorecard(snaps)
    b = compute_scorecard(snaps)
    assert a == b
    assert a.compounding_score == b.compounding_score
    assert (
        a.axis_convergence,
        a.axis_gotcha_learning,
        a.axis_verify_non_regression,
        a.axis_enrichment,
    ) == (
        b.axis_convergence,
        b.axis_gotcha_learning,
        b.axis_verify_non_regression,
        b.axis_enrichment,
    )


def test_compounding_score_unaffected_by_multi_judge_scores():
    """Under the multi-judge aggregation path, the judge output does NOT feed
    compute_scorecard: compounding_score for the SAME snapshots is unchanged whether the
    judges all score 0 or all score 10 (the LLM judge is excluded from the mechanical
    scorer — IND-03)."""
    snaps = _fixed_snapshots()
    baseline = compute_scorecard(snaps).compounding_score

    all_low = aggregate_judges(
        [JudgeResult(0, 0, ""), JudgeResult(1, 0, ""), JudgeResult(2, 0, "")]
    )
    all_high = aggregate_judges(
        [JudgeResult(0, 10, ""), JudgeResult(1, 10, ""), JudgeResult(2, 10, "")]
    )
    # The two multi-judge aggregations genuinely differ...
    assert all_low["mean"] != all_high["mean"]
    assert all_low["majority_pass"] is False and all_high["majority_pass"] is True
    # ...yet the mechanical score is invariant to them.
    assert compute_scorecard(snaps).compounding_score == baseline


def test_write_json_marks_judge_excluded_under_multi_judge(tmp_path: Path):
    """write_json emits the judge block with its 'EXCLUDED from compounding_score' note
    when multi-judge results are present, and the payload's compounding_score equals the
    scorecard-only value (judge never contaminates the metric)."""
    snaps = _fixed_snapshots()
    scorecard = compute_scorecard(snaps)
    out = tmp_path / "r.json"
    # A multi-judge set (>=2 scored judges) drives the aggregation path.
    write_json(
        scorecard,
        out,
        judge_results=[JudgeResult(0, 6, "a"), JudgeResult(1, 8, "b"), JudgeResult(2, 9, "c")],
    )
    payload = json.loads(out.read_text())
    assert "EXCLUDED from compounding_score" in payload["judge"]["note"]
    assert payload["compounding_score"] == scorecard.compounding_score
