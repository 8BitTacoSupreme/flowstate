"""N-trial replication of the memory on/off A/B for a statistical effect size.

Runs the compound_eval harness N times per arm (--inject on vs off), each K live runs
with the Tier-2 judge, then aggregates the per-run judge scores across trials and
reports per-arm mean±std, per-trial improvement (last-first), and the effect size
(Cohen's d) of on-arm vs off-arm improvement. This averages out the single-trial
run-0 noise that made the first A/B directional rather than measured.

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


def _run_trial(inject: str, runs: int, root: Path, label: str) -> list[float] | None:
    """One harness invocation; returns the per-run judge scores, or None on any gap."""
    out = Path(tempfile.mkstemp(prefix=f"repl_{label}_", suffix=".json")[1])
    cmd = [
        sys.executable, "-m", "bench.compound_eval",
        "--mode", "real", "--inject", inject, "--runs", str(runs),
        "--root", str(root), "--judge", "--allow-llm", "--out", str(out),
    ]  # fmt: skip
    subprocess.run(cmd, check=False)
    try:
        d = json.loads(out.read_text())
        scores = [r["score"] for r in d.get("judge", {}).get("per_run", [])]
    except Exception:
        return None
    if not scores or any(s is None for s in scores):
        return None
    return [float(s) for s in scores]


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
    a = ap.parse_args(argv)

    collected: dict[str, list[list[float]]] = {"on": [], "off": []}
    for inject in ("on", "off"):
        for t in range(a.trials):
            scores = _run_trial(inject, a.runs, a.root, f"{inject}{t}")
            print(f"[replicate] {inject} trial {t}: {scores}", flush=True)
            if scores is not None:
                collected[inject].append(scores)

    summary = {
        "trials_requested": a.trials,
        "runs_per_trial": a.runs,
        "on": _agg(collected["on"]),
        "off": _agg(collected["off"]),
    }
    summary["effect_size_cohens_d"] = _cohens_d(summary["on"], summary["off"])
    summary["improvement_delta_on_minus_off"] = (
        round(summary["on"]["improvement_mean"] - summary["off"]["improvement_mean"], 2)
        if collected["on"] and collected["off"]
        else None
    )
    print(json.dumps(summary, indent=2))
    if a.out:
        Path(a.out).write_text(json.dumps(summary, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
