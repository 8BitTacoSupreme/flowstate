"""Tests for bench/close_loop.py — the one-command
prior-runs->distill->inject->judge->CI driver.

Covers:
- cheap-mode end-to-end run against the checked-in fixture, asserting a CI'd
  delta is returned (not a single-shot score), with no claude binary required.
- non-mutation: the checked-in fixture stays clean after a cheap run (all
  writes land in the isolated ``_worktree`` copy).
- determinism: two identical same-seed cheap runs produce identical CI bounds.
- real-path plumbing: monkeypatches ``bench.replicate._run_trial`` and
  ``bench.prepare_fixture.main`` so no live LLM/subprocess is ever invoked.
"""

from __future__ import annotations

import json
from pathlib import Path

import bench.prepare_fixture as prepare_fixture
import bench.replicate as replicate
from bench.close_loop import main

_FIXTURE = "bench/fixtures/sample_project"


def test_cheap_mode_returns_ci_delta_end_to_end(tmp_path):
    """--mode cheap on the checked-in fixture returns a CI'd delta, not a bare score."""
    out = tmp_path / "result.json"
    rc = main(
        ["--root", _FIXTURE, "--mode", "cheap", "--trials", "3", "--runs", "3", "--out", str(out)]
    )

    assert rc == 0
    result = json.loads(out.read_text())
    ci = result["bootstrap_ci_delta_vs_baseline"]
    assert isinstance(ci["mean"], float)
    assert isinstance(ci["ci_low"], float)
    assert isinstance(ci["ci_high"], float)
    assert ci["ci_low"] <= ci["mean"] <= ci["ci_high"]
    assert "EXCLUDED from compounding_score" in result["note"]


def test_cheap_mode_does_not_mutate_checked_in_fixture(tmp_path):
    """The isolated worktree, not the checked-in fixture, holds the seeded memory + wiki corpus."""
    out = tmp_path / "result.json"
    rc = main(
        ["--root", _FIXTURE, "--mode", "cheap", "--trials", "2", "--runs", "2", "--out", str(out)]
    )

    assert rc == 0
    assert not Path(f"{_FIXTURE}/memory.db").exists()
    assert not Path(f"{_FIXTURE}/.planning/codebase/wiki").exists()


def test_cheap_mode_same_seed_is_deterministic(tmp_path):
    """Two identical --mode cheap invocations with the same --seed agree on CI bounds."""
    out1 = tmp_path / "r1.json"
    out2 = tmp_path / "r2.json"
    argv_common = [
        "--root",
        _FIXTURE,
        "--mode",
        "cheap",
        "--trials",
        "3",
        "--runs",
        "3",
        "--seed",
        "42",
    ]

    assert main([*argv_common, "--out", str(out1)]) == 0
    assert main([*argv_common, "--out", str(out2)]) == 0

    ci1 = json.loads(out1.read_text())["bootstrap_ci_delta_vs_baseline"]
    ci2 = json.loads(out2.read_text())["bootstrap_ci_delta_vs_baseline"]
    assert ci1["mean"] == ci2["mean"]
    assert ci1["ci_low"] == ci2["ci_low"]
    assert ci1["ci_high"] == ci2["ci_high"]


def test_real_mode_plumbing_uses_monkeypatched_run_trial_no_subprocess(tmp_path, monkeypatch):
    """--mode real reuses replicate._run_trial and prepare_fixture.main.

    Both are monkeypatched here so no live claude subprocess is ever invoked;
    the fixed trajectories still produce a well-formed CI'd delta.
    """
    calls: list[tuple[str, str]] = []

    def fake_run_trial(arm, runs, root, label):
        calls.append((arm, label))
        # arm trends up (improvement=2), baseline stays flat (improvement=0)
        # -> every paired per-trial delta is exactly 2.0 (deterministic CI).
        return [5.0, 6.0, 7.0] if arm == "wiki" else [5.0, 5.0, 5.0]

    def fake_prepare_fixture_main(argv):
        return 0

    monkeypatch.setattr(replicate, "_run_trial", fake_run_trial)
    monkeypatch.setattr(prepare_fixture, "main", fake_prepare_fixture_main)

    out = tmp_path / "real_result.json"
    rc = main(
        [
            "--root",
            _FIXTURE,
            "--mode",
            "real",
            "--arm",
            "wiki",
            "--baseline",
            "none",
            "--trials",
            "3",
            "--runs",
            "3",
            "--out",
            str(out),
        ]
    )

    assert rc == 0
    assert calls, "expected the monkeypatched replicate._run_trial to be invoked"
    assert {arm for arm, _ in calls} == {"wiki", "none"}

    result = json.loads(out.read_text())
    ci = result["bootstrap_ci_delta_vs_baseline"]
    assert ci["n"] == 3
    assert ci["mean"] == 2.0
    assert ci["ci_low"] == 2.0
    assert ci["ci_high"] == 2.0


def test_real_mode_pairs_by_trial_index_when_arm_trial_drops(tmp_path, monkeypatch):
    """CR-01: an arm trial that fails (None) while the baseline trial succeeds must
    drop the WHOLE pair for that trial index, keeping the survivors trial-aligned.

    arm improvements: [3, -, 2]; baseline improvements: [1, 0.5, 1]. Correct
    trial-index pairing keeps trials 0 and 2 -> deltas [3-1, 2-1] = [2.0, 1.0]
    -> n 2, mean 1.5. Positional survivor-compaction (the bug) would instead
    pair arm[2] with baseline[1] and give a different result.
    """
    arm_seq = {0: [5.0, 6.0, 8.0], 1: None, 2: [5.0, 6.0, 7.0]}
    base_seq = {0: [5.0, 5.5, 6.0], 1: [5.0, 5.0, 5.5], 2: [5.0, 6.0, 6.0]}

    def fake_run_trial(arm, runs, root, label):
        t = int(label[-1])  # label is f"{arm}{t}"
        return arm_seq[t] if arm == "wiki" else base_seq[t]

    monkeypatch.setattr(replicate, "_run_trial", fake_run_trial)
    monkeypatch.setattr(prepare_fixture, "main", lambda argv: 0)

    out = tmp_path / "r.json"
    rc = main(
        [
            "--root",
            _FIXTURE,
            "--mode",
            "real",
            "--arm",
            "wiki",
            "--baseline",
            "none",
            "--trials",
            "3",
            "--runs",
            "3",
            "--out",
            str(out),
        ]
    )
    assert rc == 0
    ci = json.loads(out.read_text())["bootstrap_ci_delta_vs_baseline"]
    assert ci["n"] == 2
    assert ci["mean"] == 1.5
    assert ci["ci_low"] <= ci["mean"] <= ci["ci_high"]
