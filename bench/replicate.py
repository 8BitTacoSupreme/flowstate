"""N-trial replication across multiple layer arms for per-arm Cohen's d effect size.

Runs the compound_eval harness N times per arm (--layers choices), each K live runs
with the Tier-2 judge, then aggregates the per-run judge scores across trials and
reports per-arm mean±std, paired-normalized per-trial trajectories, per-arm
improvement (last-first), and the effect size (Cohen's d) of each arm vs the `none`
arm. This averages out the single-trial run-0 noise that made the first A/B
directional rather than measured.

Optional --paired normalization: subtracts each trial's run-0 score from all of that
trial's scores so cross-arm run-0 baseline noise cancels out (each trajectory starts
at 0). Raw scores are ALWAYS retained alongside paired.

Research driver (long, real LLM cost). Run:
    python -m bench.replicate --trials 5 --runs 3 --root bench/fixtures/sample_project
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path

from bench.bootstrap import paired_bootstrap_ci

# Distinct judge/producer models threaded into the compound_eval subprocess so the
# real replicate/close_loop path passes the independence guard (D-06) AND stays
# runnable: judge != producer is REQUIRED by the compound_eval guard. Kept as
# module-level constants so _run_trial's call-site signature stays unchanged and the
# existing whole-function / subprocess.run monkeypatch tests remain valid.
_JUDGE_MODEL = "claude-opus-4-1"
_PRODUCER_MODEL = "claude-sonnet-4-5"


def _run_trial(arm: str, runs: int, root: Path, label: str) -> list[float] | None:
    """One harness invocation; returns the per-run judge scores.

    Three failure classes, handled distinctly:
      1. Harness gap — nonzero compound_eval subprocess returncode: prints a
         diagnostic and returns None.
      2. Output gap — the output file is missing or unreadable (OSError): prints
         a diagnostic and returns None.
      3. Judge-output contract violation — malformed JSON or a per_run row
         missing its 'score' key: propagates (json.JSONDecodeError / KeyError /
         TypeError) instead of being swallowed, so a contract violation is never
         silently averaged into the CI as a mere trial gap.
    """
    # mkstemp returns (open_fd, path); close the fd immediately so it does not
    # leak, and unlink the file in the finally below so a full sweep
    # (trials x arms x 2 invocations) cannot exhaust the fd limit or litter TMPDIR.
    fd, path = tempfile.mkstemp(prefix=f"repl_{label}_", suffix=".json")
    os.close(fd)
    out = Path(path)
    cmd = [
        sys.executable,
        "-m",
        "bench.compound_eval",
        "--mode",
        "real",
        "--layers",
        arm,
        "--runs",
        str(runs),
        "--root",
        str(root),
        "--judge",
        "--allow-llm",
        # judge != producer is required by the compound_eval independence guard (D-06);
        # a bare --judge --allow-llm with no models would now abort with _EXIT_JUDGE_CONFIG.
        "--judge-model",
        _JUDGE_MODEL,
        "--producer-model",
        _PRODUCER_MODEL,
        "--out",
        str(out),
    ]
    try:
        proc = subprocess.run(cmd, check=False)
        if proc.returncode != 0:
            print(f"[replicate] {label}: compound_eval exited {proc.returncode}", flush=True)
            return None
        raw = out.read_text()
    except OSError as exc:
        print(f"[replicate] {label}: no/unreadable output ({exc})", flush=True)
        return None
    finally:
        out.unlink(missing_ok=True)

    d = json.loads(raw)
    scores = [r["score"] for r in d.get("judge", {}).get("per_run", [])]
    if not scores or any(s is None for s in scores):
        return None
    return [float(s) for s in scores]


def _paired_normalize(trials: list[list[float]]) -> list[list[float]]:
    """Subtract each trial's run-0 score from all of that trial's scores.

    Each normalized trajectory starts at 0 — cancels cross-arm run-0 baseline
    noise while preserving inter-run deltas.  Translation-invariant: the
    improvement (last - first) is unchanged by normalization.
    """
    return [[s - t[0] for s in t] for t in trials]


def _agg(trials: list[list[float]]) -> dict:
    # Std uses statistics.pstdev (population SD, ddof=0), NOT the conventional
    # sample SD (ddof=1). This is deliberate: a single trial (n=1) is a
    # legitimate input here, and statistics.stdev raises StatisticsError for
    # n<2 — pstdev degenerates cleanly to 0.0 instead. The ddof=0 choice
    # slightly deflates the SD vs ddof=1, which is acceptable because these
    # numbers feed a DIRECTIONAL effect-size readout (Cohen's d sign/magnitude
    # band), not an inferential test. Keeping the never-raises single-trial path
    # is worth the small deflation; see _cohens_d for the matching pooling note.
    if not trials:
        return {"n": 0}
    k = min(len(s) for s in trials)
    improvements = [s[k - 1] - s[0] for s in trials]
    return {
        "n": len(trials),
        "per_run_mean": [round(statistics.mean(s[i] for s in trials), 2) for i in range(k)],
        "per_run_std": [round(statistics.pstdev([s[i] for s in trials]), 2) for i in range(k)],
        "improvement_mean": round(statistics.mean(improvements), 2),
        "improvement_std": round(statistics.pstdev(improvements), 2),
        "improvements": improvements,
    }


def _per_trial_improvements(trials: list[list[float] | None]) -> list[float | None]:
    """Per-trial improvement (last - first), aligned to trial index, None-preserving.

    Unlike ``_agg`` (which aggregates over the surviving trials and loses trial
    identity), this keeps a slot per trial index: a missing trial (``None``) stays
    ``None`` so callers can pair two arms by trial index and drop a pair only when
    either side is absent. Improvement is translation-invariant, so raw and
    paired-normalized trajectories yield identical per-trial improvements.
    """
    present = [t for t in trials if t is not None]
    if not present:
        return [None] * len(trials)
    k = min(len(t) for t in present)
    return [t[k - 1] - t[0] if t is not None else None for t in trials]


def _cohens_d(on: dict, off: dict) -> float | None:
    if on.get("n", 0) < 2 or off.get("n", 0) < 2:
        return None
    # Equal-weight pooling: sqrt((s_on**2 + s_off**2)/2) assumes the two arms
    # have equal n. With unequal surviving-trial counts the n-weighted pooled
    # SD sqrt(((n1-1)s1**2 + (n2-1)s2**2)/(n1+n2-2)) would be more precise, but
    # the inputs are population SDs (see _agg's ddof=0 note) feeding a
    # directional effect-size band, not an inferential test — the equal-weight
    # simplification is acceptable here and avoids reintroducing the n<2 crash
    # path that the sample-SD form would require.
    s_pooled = ((on["improvement_std"] ** 2 + off["improvement_std"] ** 2) / 2) ** 0.5
    if s_pooled == 0:
        return None
    return round((on["improvement_mean"] - off["improvement_mean"]) / s_pooled, 2)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="bench.replicate")
    ap.add_argument("--trials", type=int, default=5)
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--root", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument(
        "--layers",
        nargs="+",
        choices=("full", "pack", "memory", "none", "wiki"),
        default=["full", "pack", "memory", "none"],
        help="Layer arms to replicate. Default: all four arms.",
    )
    ap.add_argument(
        "--paired",
        action="store_true",
        help=(
            "Subtract each trial's run-0 from its own scores before aggregating "
            "(cancels cross-arm run-0 baseline noise)."
        ),
    )
    a = ap.parse_args(argv)

    # Keep a per-trial slot (with None holes for failed trials) so trial identity
    # survives — the paired-bootstrap CI below pairs arm vs none BY TRIAL INDEX,
    # not by compacted survivor position.
    collected: dict[str, list[list[float] | None]] = {arm: [None] * a.trials for arm in a.layers}
    for arm in a.layers:
        for t in range(a.trials):
            scores = _run_trial(arm, a.runs, a.root, f"{arm}{t}")
            print(f"[replicate] {arm} trial {t}: {scores}", flush=True)
            collected[arm][t] = scores

    # Build per-arm raw + paired aggregates over the SURVIVING trials (None holes
    # dropped for the summary stats; trial-index identity is preserved in
    # `collected` for the paired-bootstrap CI below).
    arms_summary: dict[str, dict] = {}
    for arm in a.layers:
        trials = [t for t in collected[arm] if t is not None]
        raw_agg = _agg(trials)
        norm_agg = _agg(_paired_normalize(trials)) if trials else {"n": 0}
        arms_summary[arm] = {"raw": raw_agg, "paired": norm_agg}

    # Metric driving Cohen's d: paired when --paired requested, raw otherwise
    metric = "paired" if a.paired else "raw"

    # Per-arm Cohen's d vs the none arm (when none is present in the run)
    effect_sizes: dict[str, float | None] = {}
    for arm in a.layers:
        if arm == "none":
            continue
        if "none" in arms_summary:
            effect_sizes[arm] = _cohens_d(arms_summary[arm][metric], arms_summary["none"][metric])
        else:
            effect_sizes[arm] = None

    summary: dict = {
        "trials_requested": a.trials,
        "runs_per_trial": a.runs,
        "layers": a.layers,
        "paired_mode": a.paired,
        "metric_for_effect_size": metric,
        "arms": arms_summary,
        "effect_size_cohens_d": effect_sizes,
    }

    # Retain improvement_delta vs none per arm (for both raw and paired metrics)
    if "none" in arms_summary:
        deltas: dict[str, dict | None] = {}
        for arm in a.layers:
            if arm == "none":
                continue
            none_raw = arms_summary["none"]["raw"]
            none_paired = arms_summary["none"]["paired"]
            arm_raw = arms_summary[arm]["raw"]
            arm_paired = arms_summary[arm]["paired"]
            deltas[arm] = {
                "raw": (
                    round(arm_raw["improvement_mean"] - none_raw["improvement_mean"], 2)
                    if arm_raw.get("n", 0) > 0 and none_raw.get("n", 0) > 0
                    else None
                ),
                "paired": (
                    round(arm_paired["improvement_mean"] - none_paired["improvement_mean"], 2)
                    if arm_paired.get("n", 0) > 0 and none_paired.get("n", 0) > 0
                    else None
                ),
            }
        summary["improvement_delta_vs_none"] = deltas

        # Track-2 only: seeded paired-bootstrap CI on per-trial deltas
        # (arm_improvement_t - none_improvement_t), paired by TRIAL INDEX. A pair
        # is kept only when BOTH arm and none produced a score for that trial; a
        # unilateral failure drops the whole pair so the two sides stay
        # index-aligned. Improvement is translation-invariant, so this matches the
        # selected `metric` (raw/paired) exactly. Isolated from the scorecard module.
        none_improvements = _per_trial_improvements(collected["none"])
        ci_deltas: dict[str, dict] = {}
        for arm in a.layers:
            if arm == "none":
                continue
            arm_improvements = _per_trial_improvements(collected[arm])
            paired_deltas = [
                arm_improvements[t] - none_improvements[t]
                for t in range(a.trials)
                if arm_improvements[t] is not None and none_improvements[t] is not None
            ]
            ci_deltas[arm] = paired_bootstrap_ci(paired_deltas)
        summary["bootstrap_ci_delta_vs_none"] = ci_deltas

    print(json.dumps(summary, indent=2))
    if a.out:
        Path(a.out).write_text(json.dumps(summary, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
