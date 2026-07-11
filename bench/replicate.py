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
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path

from bench.bootstrap import paired_bootstrap_ci


def _run_trial(arm: str, runs: int, root: Path, label: str) -> list[float] | None:
    """One harness invocation; returns the per-run judge scores, or None on any gap."""
    out = Path(tempfile.mkstemp(prefix=f"repl_{label}_", suffix=".json")[1])
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
        "--out",
        str(out),
    ]
    subprocess.run(cmd, check=False)
    try:
        d = json.loads(out.read_text())
        scores = [r["score"] for r in d.get("judge", {}).get("per_run", [])]
    except Exception:
        return None
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


def _cohens_d(on: dict, off: dict) -> float | None:
    if on.get("n", 0) < 2 or off.get("n", 0) < 2:
        return None
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

    collected: dict[str, list[list[float]]] = {arm: [] for arm in a.layers}
    for arm in a.layers:
        for t in range(a.trials):
            scores = _run_trial(arm, a.runs, a.root, f"{arm}{t}")
            print(f"[replicate] {arm} trial {t}: {scores}", flush=True)
            if scores is not None:
                collected[arm].append(scores)

    # Build per-arm raw + paired aggregates
    arms_summary: dict[str, dict] = {}
    for arm in a.layers:
        trials = collected[arm]
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
        # (arm_improvement_t - none_improvement_t), paired by trial index.
        # Stays isolated from the deterministic scorecard module.
        none_improvements = arms_summary["none"][metric].get("improvements", [])
        ci_deltas: dict[str, dict] = {}
        for arm in a.layers:
            if arm == "none":
                continue
            arm_improvements = arms_summary[arm][metric].get("improvements", [])
            k = min(len(arm_improvements), len(none_improvements))
            paired_deltas = [arm_improvements[i] - none_improvements[i] for i in range(k)]
            ci_deltas[arm] = paired_bootstrap_ci(paired_deltas)
        summary["bootstrap_ci_delta_vs_none"] = ci_deltas

    print(json.dumps(summary, indent=2))
    if a.out:
        Path(a.out).write_text(json.dumps(summary, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
