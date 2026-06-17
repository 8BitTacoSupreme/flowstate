"""Checkable grounding-eval harness — binary multi-judge signal for context-layer value.

For each (arm, probe): inject the arm's context prefix via build_context_prefix, ask the
probe question via ``claude --print``, then K judges binary fact-check the answer against
ground truth. Arm score = grounding accuracy (% probes majority-correct) with Wilson
score confidence intervals — lower variance than a 0-10 vibe judge.

ADD-ONLY: do NOT modify pipeline, judge, replicate, compound_eval, or context_prefix.
Research tooling only — no UI, never-raises throughout, stdlib only
(math/json/subprocess/argparse/re/os/sys).
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
import sys
from pathlib import Path

from bench.compound_eval import _LAYERS_MAP
from bench.judge import _locate_claude
from flowstate.context_prefix import build_context_prefix
from flowstate.memory import MemoryStore

# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────

_ANSWER_MAX_ATTEMPTS = 3
_ANSWER_TIMEOUT = 180
_JUDGE_TIMEOUT = 60

# Matches the first YES or NO token in a response (case-insensitive).
_YESNO_RE = re.compile(r"\b(yes|no)\b", re.IGNORECASE)


# ──────────────────────────────────────────────────────────────────────────────
# Probes loader
# ──────────────────────────────────────────────────────────────────────────────


def _load_probes(path: Path) -> list[dict] | None:
    """Read and validate a probes JSON file. Never raises.

    Returns a list of probe dicts (each with keys id/question/ground_truth) on
    success, or None on missing file, parse error, non-list result, or empty list.
    Makes NO subprocess calls.
    """
    try:
        data = json.loads(path.read_text())
        if not isinstance(data, list) or not data:
            return None
        return data
    except Exception:
        return None


# ──────────────────────────────────────────────────────────────────────────────
# Wilson score interval
# ──────────────────────────────────────────────────────────────────────────────


def _wilson(successes: int, n: int) -> tuple[float, float]:
    """Wilson score confidence interval at z=1.96. Never raises.

    Returns (low, high) clamped to [0,1]. n==0 returns (0.0, 0.0).
    """
    if n == 0:
        return (0.0, 0.0)
    z = 1.96
    z2 = z * z
    phat = successes / n
    center = (phat + z2 / (2 * n)) / (1 + z2 / n)
    half = (z / (1 + z2 / n)) * math.sqrt(phat * (1 - phat) / n + z2 / (4 * n * n))
    low = max(0.0, center - half)
    high = min(1.0, center + half)
    return (low, high)


# ──────────────────────────────────────────────────────────────────────────────
# Answer helper
# ──────────────────────────────────────────────────────────────────────────────


def _answer(prefix: str, question: str, model: str) -> str:
    """Ask a question via ``claude --print`` with an optional context prefix. Never raises.

    Returns the answer string, or "" when no claude binary is found or all attempts fail.
    Retries up to _ANSWER_MAX_ATTEMPTS times, skipping empty stdout or non-zero returncode
    (mirrors the research.py empty-then-good retry idiom).
    """
    claude = _locate_claude()
    if claude is None:
        return ""
    prompt = (
        (prefix + "\n\n---\n\n" if prefix else "")
        + "Question: "
        + question
        + "\nAnswer concisely and specifically."
    )
    cmd = [claude, "--print", "--max-turns", "1", "--model", model, "--", prompt]
    for _ in range(_ANSWER_MAX_ATTEMPTS):
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=_ANSWER_TIMEOUT)
            if proc.returncode == 0 and proc.stdout.strip():
                return proc.stdout.strip()
        except Exception:
            pass
    return ""


# ──────────────────────────────────────────────────────────────────────────────
# Fact-check helper
# ──────────────────────────────────────────────────────────────────────────────


def _factcheck(answer: str, ground_truth: str, model: str) -> bool | None:
    """Binary fact-check: does the answer correctly state the ground truth? Never raises.

    Returns True (YES), False (NO), or None (unparseable/error/no bridge).
    One call, no retry.
    """
    claude = _locate_claude()
    if claude is None:
        return None
    prompt = (
        "Does the ANSWER correctly state this FACT? Reply with ONLY 'YES' or 'NO'.\n\n"
        "FACT: " + ground_truth + "\n\nANSWER: " + answer
    )
    cmd = [claude, "--print", "--max-turns", "1", "--model", model, "--", prompt]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=_JUDGE_TIMEOUT)
        if proc.returncode != 0:
            return None
        m = _YESNO_RE.search(proc.stdout or "")
        if m is None:
            return None
        return m.group(1).lower() == "yes"
    except Exception:
        return None


# ──────────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bench.grounding")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--probes", type=Path, required=True)
    parser.add_argument(
        "--layers",
        nargs="+",
        choices=("full", "none", "pack", "memory", "wiki"),
        default=["none", "pack", "wiki"],
    )
    parser.add_argument("--trials", type=int, default=2)
    parser.add_argument("--answer-model", default="sonnet")
    parser.add_argument("--judge-models", default="sonnet,sonnet,opus")
    parser.add_argument("--budget-tokens", type=int, default=50000)
    parser.add_argument("--out", type=Path, default=None)
    return parser


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    """Run the grounding eval harness. Returns 0 on success, non-zero on bad input."""
    args = _build_parser().parse_args(argv)

    # Set budget env var FIRST so build_context_prefix/_load_budget can honor it.
    os.environ["FLOWSTATE_CONTEXT_BUDGET_TOKENS"] = str(args.budget_tokens)

    probes = _load_probes(args.probes)
    if probes is None:
        print(f"no usable probes in {args.probes}")
        return 1

    judge_models = [m.strip() for m in args.judge_models.split(",") if m.strip()]
    root = args.root

    # Collect per-arm records across all trials x probes.
    arm_records: dict[str, list[dict]] = {arm: [] for arm in args.layers}

    for trial in range(args.trials):
        for arm in args.layers:
            for probe in probes:
                with MemoryStore(root=root) as mem:
                    prefix = build_context_prefix(
                        root,
                        mem,
                        query=probe["question"],
                        include_layers=_LAYERS_MAP[arm],
                    )
                answer = _answer(prefix, probe["question"], args.answer_model)
                if answer == "":
                    votes = [None] * len(judge_models)
                else:
                    votes = [_factcheck(answer, probe["ground_truth"], m) for m in judge_models]
                yes = sum(1 for v in votes if v is True)
                majority = yes > len(judge_models) / 2
                arm_records[arm].append(
                    {
                        "arm": arm,
                        "trial": trial,
                        "probe_id": probe["id"],
                        "answer_chars": len(answer),
                        "votes": [
                            "YES" if v is True else "NO" if v is False else "?" for v in votes
                        ],
                        "majority": majority,
                    }
                )

    # Aggregate per arm.
    arms: dict[str, dict] = {}
    for arm, records in arm_records.items():
        n = len(records)
        successes = sum(1 for r in records if r["majority"])
        accuracy = successes / n if n else 0.0
        wilson_low, wilson_high = _wilson(successes, n)
        arms[arm] = {
            "accuracy": accuracy,
            "n": n,
            "wilson_low": wilson_low,
            "wilson_high": wilson_high,
            "per_probe": records,
        }

    # Delta vs none arm (only when "none" arm was evaluated).
    accuracy_delta_vs_none: dict[str, float] = {}
    if "none" in arms:
        accuracy_delta_vs_none = {
            a: round(arms[a]["accuracy"] - arms["none"]["accuracy"], 3) for a in arms
        }

    output = {
        "probes_file": str(args.probes),
        "n_probes": len(probes),
        "trials": args.trials,
        "answer_model": args.answer_model,
        "judge_models": judge_models,
        "arms": arms,
        "accuracy_delta_vs_none": accuracy_delta_vs_none,
    }

    if args.out is not None:
        try:
            args.out.write_text(json.dumps(output, indent=2))
        except Exception as exc:
            print(f"warning: could not write results to {args.out}: {exc}")

    # Console summary table.
    print(f"\n{'arm':<10} {'accuracy':>10} {'wilson_ci':>20} {'n':>6}")
    print("-" * 50)
    for arm, data in arms.items():
        ci = f"[{data['wilson_low']:.3f}, {data['wilson_high']:.3f}]"
        print(f"{arm:<10} {data['accuracy']:>10.3f} {ci:>20} {data['n']:>6}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
