"""bench/close_loop.py — the ONE end-to-end command closing the v0.6.2 harness loop.

Research/bench tooling, NOT a flowstate CLI subcommand. Chains
prior-runs -> distill -> inject -> judge -> paired-bootstrap CI on a fixture and
returns a CI'd delta (arm vs baseline), never a single-shot score. This is
Track-2 (judge-derived) output and is EXCLUDED from bench.metrics' deterministic
compounding_score — the bench.metrics scorecard builder is not a dependency here.

``--mode cheap`` (default) is CI-safe: it synthesizes deterministic per-trial
judge trajectories from a seeded ``random.Random``, invoking no subprocess and
requiring no ``claude`` binary. ``--mode real`` reuses
``bench.replicate._run_trial`` for live judge trajectories (research only,
real LLM cost).

DISTILL/INJECT-PREP runs inside an isolated ``_worktree`` copy of ``--root``,
seeded via ``bench.project.scaffold`` BEFORE ``bench.prepare_fixture.main``
provisions the arm's producer — mirroring ``bench.compound_eval._cheap_loop``.
The checked-in fixture at ``--root`` is therefore never mutated; all writes
land in a temp copy that is removed on exit (even on failure).

Invoke via:
    python -m bench.close_loop --root bench/fixtures/sample_project --mode cheap
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

import bench.prepare_fixture as prepare_fixture
import bench.replicate as replicate
from bench.bootstrap import _BOOTSTRAP_SEED, paired_bootstrap_ci
from bench.compound_eval import _worktree
from bench.project import scaffold

# Arms with a real producer that prepare_fixture must provision. Baseline arms
# (typically "none") never need provisioning.
_PRODUCER_ARMS = ("pack", "wiki")


def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="bench.close_loop",
        description=(
            "One command: prior-runs -> distill -> inject -> judge -> "
            "paired-bootstrap CI, on an isolated worktree copy of --root."
        ),
    )
    ap.add_argument("--root", type=Path, required=True)
    ap.add_argument("--arm", default="wiki", help="Treatment arm (default: wiki).")
    ap.add_argument("--baseline", default="none", help="Baseline arm (default: none).")
    ap.add_argument("--trials", type=int, default=5)
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--mode", choices=("cheap", "real"), default="cheap")
    ap.add_argument("--seed", type=int, default=_BOOTSTRAP_SEED)
    ap.add_argument("--out", type=Path, default=None)
    return ap


def _distill(target: Path, arm: str) -> int:
    """Seed the worktree with a baseline RUN entry, then provision ``arm``'s producer.

    ``scaffold(target)`` runs FIRST so the worktree has non-empty, distillable
    memory (the seeded baseline MemoryKind.RUN entry) before prepare_fixture's
    wiki producer is invoked. Only arms with a real producer (pack/wiki) are
    provisioned; the rest (full/memory/none) are a no-op. Returns 0 on success,
    prepare_fixture's own non-zero code on failure.
    """
    scaffold(target)
    if arm not in _PRODUCER_ARMS:
        return 0
    return prepare_fixture.main(["--root", str(target), "--arms", arm])


def _cheap_trajectories(
    seed: int, trials: int, runs: int
) -> tuple[list[list[float]], list[list[float]]]:
    """Deterministic, LLM-free per-trial judge trajectories for arm and baseline.

    A single seeded ``random.Random`` instance drives both draws sequentially,
    so the SAME seed always produces the SAME pair of trajectory sets — this is
    an apparatus check (the plumbing runs end to end), not a causal signal.
    """
    rng = random.Random(seed)
    arm_trials = [[round(rng.uniform(4.0, 9.0), 2) for _ in range(runs)] for _ in range(trials)]
    baseline_trials = [
        [round(rng.uniform(3.0, 7.0), 2) for _ in range(runs)] for _ in range(trials)
    ]
    return arm_trials, baseline_trials


def _real_trajectories(
    target: Path, arm: str, baseline: str, trials: int, runs: int
) -> tuple[list[list[float] | None], list[list[float] | None]]:
    """Live per-trial judge trajectories via ``bench.replicate._run_trial``. Real mode only.

    Preserves trial identity: a failed trial is recorded as ``None`` at its trial
    index (not compacted away), so ``_paired_deltas`` can drop the whole pair when
    either side is missing and keep arm and baseline matched by trial index.
    """
    arm_trials: list[list[float] | None] = []
    baseline_trials: list[list[float] | None] = []
    for t in range(trials):
        arm_trials.append(replicate._run_trial(arm, runs, target, f"{arm}{t}"))
        baseline_trials.append(replicate._run_trial(baseline, runs, target, f"{baseline}{t}"))
    return arm_trials, baseline_trials


def _paired_deltas(
    arm_trials: list[list[float] | None], baseline_trials: list[list[float] | None]
) -> list[float]:
    """Per-trial (arm improvement - baseline improvement), paired by TRIAL INDEX.

    A pair is kept only when BOTH sides produced a score for that trial index; a
    unilateral failure (``None`` on either side) drops the whole pair so arm and
    baseline improvements remain matched observations.
    """
    arm_improvements = replicate._per_trial_improvements(arm_trials)
    baseline_improvements = replicate._per_trial_improvements(baseline_trials)
    k = min(len(arm_improvements), len(baseline_improvements))
    return [
        arm_improvements[t] - baseline_improvements[t]
        for t in range(k)
        if arm_improvements[t] is not None and baseline_improvements[t] is not None
    ]


def main(argv: list[str] | None = None) -> int:
    """Run prior-runs -> distill -> inject -> judge -> CI. Never raises.

    Pipeline failures (e.g. a producer gate rejecting the arm, or an unexpected
    exception) return a non-zero code rather than propagating; the ``_worktree``
    contextmanager cleans up the temp copy even on the failure path.
    """
    args = _build_parser().parse_args(argv)
    root = Path(args.root)

    try:
        with _worktree(root) as target:
            print(f"[DISTILL] scaffolding + provisioning arm={args.arm!r} in isolated worktree")
            rc = _distill(target, args.arm)
            if rc != 0:
                print(f"[DISTILL] failed: prepare_fixture exited {rc}")
                return rc

            print(f"[JUDGE] mode={args.mode} trials={args.trials} runs={args.runs}")
            if args.mode == "real":
                arm_trials, baseline_trials = _real_trajectories(
                    target, args.arm, args.baseline, args.trials, args.runs
                )
            else:
                arm_trials, baseline_trials = _cheap_trajectories(args.seed, args.trials, args.runs)

            print("[CI] paired-bootstrap on per-trial judge deltas")
            deltas = _paired_deltas(arm_trials, baseline_trials)
            ci = paired_bootstrap_ci(deltas, seed=args.seed)
    except Exception as exc:  # never raise — pipeline failure is reported, not fatal
        print(f"[close_loop] pipeline error: {exc}")
        return 1

    result = {
        "mode": args.mode,
        "arm": args.arm,
        "baseline": args.baseline,
        "trials": args.trials,
        "runs": args.runs,
        "note": "Tier-2 judge CI — EXCLUDED from compounding_score",
        "bootstrap_ci_delta_vs_baseline": ci,
    }
    print(json.dumps(result, indent=2))
    if args.out is not None:
        try:
            Path(args.out).write_text(json.dumps(result, indent=2) + "\n")
        except OSError as exc:
            print(f"[close_loop] could not write --out: {exc}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
