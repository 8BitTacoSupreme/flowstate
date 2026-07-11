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

from pathlib import Path

import pytest

import bench.compound_eval as ce
from bench.judge import _validate_judges

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
