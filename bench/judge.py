"""Tier-2 LLM-as-judge — does FlowState's accumulating context improve OUTPUT quality?

The mechanical scorecard proves context *accumulates* (prefix grows, churn converges,
gotchas dedupe). It cannot tell whether the richer context makes the produced work
*better*. This judge scores each run's LLM-produced artifacts (research report +
strategy) against the fixture's ``system_contract`` + ``retrieval_questions``, so a
RISING score across runs is evidence that accumulated context improved output quality.

Decoupling: it calls the ``claude`` CLI directly via subprocess — NOT
``flowstate.bridge`` — so bench stays independent of the LLM substrate, mirroring how
FlowState locates/invokes claude. Never raises: any failure yields a ``None`` score
(reported as insufficient-data) and NEVER affects the mechanical CompoundingScore.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

_JUDGE_TIMEOUT = 180
_JUDGE_MAX_ATTEMPTS = 3
# Binarization threshold for the multi-judge pass-rate (IND-02 / D-02): a per-judge
# 0-10 score >= _PASS_THRESHOLD counts as a "pass". Explicit + documented, not magic.
# D-08 tie rule: majority-pass requires passes > n/2, so an even-N tie (e.g. 2/4) FAILS.
_PASS_THRESHOLD = 7.0
# LLM-produced artifacts worth judging (PROJECT.md/ROADMAP.md are deterministic templates).
_ARTIFACT_FILES = ("research/report.md", "research/strategy.md", "research/brief.md")
_MAX_ARTIFACT_CHARS = 8000
_SCORE_RE = re.compile(r'\{[^{}]*"score"[^{}]*\}', re.DOTALL)


@dataclass(frozen=True)
class JudgeResult:
    run_index: int
    score: float | None  # 0-10; None = could not judge (insufficient-data)
    rationale: str


def _locate_claude() -> str | None:
    """Locate the claude CLI (stdlib only; no flowstate.bridge import). Never raises."""
    try:
        env = os.environ.get("FLOWSTATE_CLAUDE_BIN")
        if env and Path(env).is_file():
            return env
        found = shutil.which("claude")
        if found:
            return found
        for c in (
            Path.home() / ".local" / "bin" / "claude",
            Path("/usr/local/bin/claude"),
            Path("/opt/homebrew/bin/claude"),
        ):
            if c.is_file():
                return str(c)
    except Exception:
        return None
    return None


def collect_artifacts(root: Path) -> str:
    """Concatenate the run's LLM-produced artifacts (truncated). Never raises."""
    parts: list[str] = []
    for rel in _ARTIFACT_FILES:
        p = root / rel
        try:
            if p.is_file():
                txt = p.read_text(errors="ignore").strip()
                if txt:
                    parts.append(f"### {rel}\n{txt}")
        except Exception:
            continue
    return "\n\n".join(parts)[:_MAX_ARTIFACT_CHARS]


def _build_prompt(fixture: dict, artifacts: str) -> str:
    contract = str(fixture.get("system_contract", ""))
    questions = "\n".join(f"- {x}" for x in (fixture.get("retrieval_questions") or []))
    gates = "\n".join(f"- {x}" for x in (fixture.get("acceptance_gates") or []))
    return (
        "You score the QUALITY of planning artifacts a tool produced for a software "
        "project. Be a strict grader.\n\n"
        f"SYSTEM CONTRACT (what the work must honor):\n{contract}\n\n"
        f"RUBRIC — the artifacts should concretely address these questions:\n{questions}\n\n"
        f"ACCEPTANCE GATES:\n{gates}\n\n"
        f"PRODUCED ARTIFACTS:\n{artifacts or '(none produced)'}\n\n"
        "Reward grounded, specific, non-generic content that addresses the contract and "
        "rubric; penalize vagueness, boilerplate, hedging, and contradiction. Output ONLY "
        'a JSON object: {"score": <integer 0-10>, "rationale": "<one sentence>"}.'
    )


def _parse_score(out: str) -> tuple[float | None, str]:
    for m in reversed(_SCORE_RE.findall(out or "")):
        try:
            d = json.loads(m)
        except Exception:
            continue
        s = d.get("score")
        if isinstance(s, (int, float)) and not isinstance(s, bool):
            return float(s), str(d.get("rationale", ""))[:200]
    return None, ""


def judge_run(
    run_index: int, artifacts: str, fixture: dict, *, model: str | None = None
) -> JudgeResult:
    """Score one run's artifacts via ``claude --print``. Never raises.

    Retries up to _JUDGE_MAX_ATTEMPTS times when the response is unparseable
    (score is None). Returns the first good score encountered, or a None-score
    result if all attempts fail.
    """
    claude = _locate_claude()
    if not claude or not artifacts.strip():
        return JudgeResult(run_index, None, "no judge bridge or no artifacts")
    cmd = [claude, "--print", "--max-turns", "1"]
    if model:
        cmd += ["--model", model]
    cmd += ["--", _build_prompt(fixture, artifacts)]
    last_rationale = "(no rationale parsed)"
    for _ in range(_JUDGE_MAX_ATTEMPTS):
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=_JUDGE_TIMEOUT)
            score, rationale = _parse_score(proc.stdout)
            if score is not None:
                return JudgeResult(run_index, score, rationale or "(no rationale parsed)")
            last_rationale = rationale or last_rationale
        except Exception as exc:
            last_rationale = f"judge error: {exc}"
    return JudgeResult(run_index, None, last_rationale)


def summarize(results: list[JudgeResult]) -> dict:
    """Trend over the per-run scores. Excluded from the mechanical CompoundingScore.

    trend: improving | flat | declining | insufficient-data (needs >=2 real scores).
    """
    scored = [r for r in results if r.score is not None]
    if len(scored) < 2:
        return {
            "scores": [r.score for r in results],
            "trend": "insufficient-data",
            "first": scored[0].score if scored else None,
            "last": scored[-1].score if scored else None,
            "delta": None,
        }
    first, last = scored[0].score, scored[-1].score
    delta = round(last - first, 2)
    trend = "improving" if delta > 0.5 else "declining" if delta < -0.5 else "flat"
    return {
        "scores": [r.score for r in results],
        "trend": trend,
        "first": first,
        "last": last,
        "delta": delta,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Independence guard (IND-01) — a config/validation-time HARD failure.
#
# This is distinct from the runtime never-raise -> None contract of judge_run (D-03):
# an empty judge set or a judge that equals the producer is *operator error*, caught
# BEFORE any judging starts, whereas a failed `claude` call is a soft None score. The
# helper is pure (no subprocess, no I/O) so both this CLI and the Wave-2 compound_eval
# caller can reuse it (D-06).
# ──────────────────────────────────────────────────────────────────────────────


def _validate_judges(judge_models: list[str], producer_model: str) -> None:
    """Fail loud on a compromised judge configuration. RAISES ``ValueError``.

    Empty judge set is a hard fail (D-06). ANY judge model equal to the producer model
    is a hard fail (D-04/D-07) — not merely the aggregate, EVERY judge must differ. Pure
    validation: no subprocess, no I/O, so callers reuse it at config/validate time.
    """
    if not judge_models:
        raise ValueError(
            "no judge model configured — refusing to judge (independence guard, IND-01)"
        )
    dupes = sorted({m for m in judge_models if m == producer_model})
    if dupes:
        raise ValueError(
            f"judge model(s) {dupes} equal the producer model {producer_model!r} — a judge "
            "must not grade its own producer (independence guard, IND-01)"
        )


def aggregate_judges(results: list[JudgeResult]) -> dict:
    """Multi-judge verdict (IND-02). Never raises (composes never-raise ``judge_run``).

    Keeps the 0-10 signal (mean/median of per-judge scores) AND adds a binarized
    pass-rate with a Wilson CI (D-01/D-02): each judge's score is binarized at
    ``_PASS_THRESHOLD`` (``>=`` = pass). None (insufficient-data) per-judge scores are
    EXCLUDED from the pass-rate denominator — an unusable judge does not vote (documented
    choice; mirrors ``summarize``'s None-filter). Majority-pass is conservative per D-08:
    ``passes > n/2``, so an even-N tie (e.g. 2/4) is NOT a majority -> FAIL.

    This is an ADDITIONAL surface — ``summarize()``'s numeric 0-10 trend is unchanged.
    """
    # Function-scope import: grounding.py imports from bench.judge, so a module-top
    # `from bench.grounding import _wilson` would create a circular import.
    from bench.grounding import _wilson

    scored = [r.score for r in results if r.score is not None]
    n = len(scored)
    if n == 0:
        return {
            "n_judges": len(results),
            "n_scored": 0,
            "mean": None,
            "median": None,
            "pass_threshold": _PASS_THRESHOLD,
            "passes": 0,
            "pass_rate": None,
            "wilson_low": 0.0,
            "wilson_high": 0.0,
            "majority_pass": False,
        }
    passes = sum(1 for s in scored if s >= _PASS_THRESHOLD)
    low, high = _wilson(passes, n)
    return {
        "n_judges": len(results),
        "n_scored": n,
        "mean": round(statistics.fmean(scored), 4),
        "median": round(statistics.median(scored), 4),
        "pass_threshold": _PASS_THRESHOLD,
        "passes": passes,
        "pass_rate": round(passes / n, 4),
        "wilson_low": round(low, 4),
        "wilson_high": round(high, 4),
        # D-08: passes > n/2 — an even-N tie (2/4) is not a majority, so it fails.
        "majority_pass": passes > n / 2,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bench.judge",
        description="LLM-as-judge independence guard + validate surface (IND-01).",
    )
    parser.add_argument(
        "--producer-model",
        required=True,
        help="Model that PRODUCED the artifacts under judgement. No judge may equal it.",
    )
    parser.add_argument(
        "--judge-model",
        default=None,
        help=(
            "Judge model(s). Comma-separate for the multi-judge case (e.g. 'sonnet,opus'). "
            "Every judge must differ from --producer-model. Absent => hard fail (IND-01)."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Validate judge independence (IND-01). Returns 0 when clean, nonzero on violation.

    The guard fires at validate time, BEFORE any judging — an absent judge model or a
    judge equal to the producer prints an operator-facing error and returns 1 (D-03/D-04).
    """
    args = _build_parser().parse_args(argv)
    judge_models = [m.strip() for m in (args.judge_model or "").split(",") if m.strip()]
    try:
        _validate_judges(judge_models, args.producer_model)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(
        f"ok: {len(judge_models)} judge model(s) {judge_models} distinct from "
        f"producer {args.producer_model!r}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
