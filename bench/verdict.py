"""bench/verdict.py — the pre-registered 4-contrast verdict driver (Phase 22).

Turns the already-shipped measurement stack (close_loop / replicate / bootstrap /
judge / report) into ONE pre-registered verdict: pack/memory/wiki/full each vs none,
per-contrast paired-bootstrap CI + two-sided bootstrap p + Cohen's d, Holm-Bonferroni
GATING across the 4 co-primary contrasts, and (Plan 03) a 22-VERDICT.md carrying
per-arm quality + tax + the compounding curve + PASS/NULL per the frozen D-02 rule.

It adds NO new measurement primitive and NO reimplemented statistics — it orchestrates
and interprets. It implements the FROZEN win rule from 22-PREREGISTRATION.md VERBATIM
(D-02): a treatment arm WINS iff, for its (arm - none) quality-delta contrast, ALL
THREE hold — (1) the paired-bootstrap 95% CI excludes 0, (2) Cohen's d >= 0.8, AND
(3) the contrast survives Holm-Bonferroni across the 4 co-primary contrasts (D-06 —
GATING, not decorative). Anything else = NULL, a valid, documented outcome that
licenses stripping that layer.

``--mode cheap`` (default) is deterministic + free: it synthesizes all 5 arms from one
seeded ``random.Random`` (mirroring ``close_loop._cheap_trajectories``) so the whole
driver + Holm + report proves out end-to-end with zero ``claude`` spend. ``--mode real``
reuses ``replicate``'s harness call (distinct judge/producer models, D-06 independence)
on an isolated ``compound_eval._worktree`` copy of ``--root``; the real repo is never
mutated (D-01).
"""

from __future__ import annotations

import argparse
import json
import os
import random
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import bench.prepare_fixture as prepare_fixture
import bench.replicate as replicate
from bench import report
from bench.bootstrap import paired_bootstrap_ci, paired_bootstrap_p
from bench.close_loop import _EXIT_NO_PAIRED_DATA, _PRODUCER_ARMS
from bench.compound_eval import _worktree
from bench.ground import ground_from_repo
from bench.judge import JudgeResult, aggregate_judges
from bench.metrics import RunSnapshot
from bench.project import scaffold

# The 5 pre-registered arms (D-05). "none" is the baseline; the other four are the
# co-primary treatment arms, each contrasted against none.
_ARMS = ("none", "pack", "memory", "wiki", "full")
_TREATMENTS = ("pack", "memory", "wiki", "full")

# Frozen pre-registered posture (D-08): seed pinned for reproducibility.
_PREREG_SEED = 20260711
_PREREG_DOC = ".planning/phases/22-the-verdict/22-PREREGISTRATION.md"

# Cohen's d large-effect threshold (D-02 gate 2).
_LARGE_D = 0.8

# Per-arm synthetic score ranges for cheap mode. These order the arms only so the
# report format is exercised over distinguishable numbers; the result is stamped
# synthetic=True precisely because this is an apparatus check, NOT a causal signal.
_CHEAP_RANGES = {
    "none": (3.0, 6.0),
    "pack": (3.5, 6.5),
    "memory": (4.0, 7.0),
    "wiki": (4.5, 7.5),
    "full": (5.0, 8.0),
}


# ── Holm-Bonferroni (D-06 — the GATING multiple-comparison correction) ─────────
def holm_bonferroni(pvalues: list[float | None], alpha: float = 0.05) -> list[dict]:
    """Holm step-down correction across the co-primary contrasts. Pure stdlib.

    Returns one row per input contrast, IN ORIGINAL ORDER:
    ``{"raw_p", "holm_p", "reject"}``. The adjusted p is
    ``max`` over the ascending prefix of ``(m - rank) * p``, capped at 1.0, so it is
    monotone non-decreasing in sorted order; a contrast rejects iff its adjusted p is
    below ``alpha``. A ``None`` p-value (an unmeasurable contrast) is treated as
    non-significant (``holm_p=None``, ``reject=False``) and never rejects. Never raises.

    The WIN/null decision (D-02 gate 3) uses this Holm-corrected reject flag — it is
    GATING, not decorative: a contrast that does not survive Holm cannot win regardless
    of its raw CI or d.
    """
    m = len(pvalues)
    # Sort ascending by p, pushing None (unmeasurable) to the end.
    order = sorted(
        range(m),
        key=lambda i: (pvalues[i] is None, pvalues[i] if pvalues[i] is not None else 0.0),
    )
    holm: list[float | None] = [None] * m
    running = 0.0
    for rank, idx in enumerate(order):
        p = pvalues[idx]
        if p is None:
            holm[idx] = None
            continue
        adj = min(1.0, (m - rank) * p)
        # Step-down monotonicity: the adjusted p never decreases along sorted order.
        running = max(running, adj)
        holm[idx] = running
    return [
        {
            "raw_p": pvalues[i],
            "holm_p": holm[i],
            "reject": holm[i] is not None and holm[i] < alpha,
        }
        for i in range(m)
    ]


# ── The D-02 three-part gate (CI-excludes-0 AND d>=0.8 AND Holm-reject) ─────────
def _ci_excludes_zero(ci: dict) -> bool:
    """True iff the paired-bootstrap CI lies entirely on one side of 0 (D-02 gate 1)."""
    lo, hi = ci.get("ci_low"), ci.get("ci_high")
    if lo is None or hi is None:
        return False
    return lo > 0 or hi < 0


def _gate(ci: dict, *, cohens_d: float | None, holm_reject: bool) -> str:
    """The frozen D-02 win rule VERBATIM. Returns ``"pass"`` iff ALL THREE hold.

    (1) the paired-bootstrap 95% CI excludes 0, (2) Cohen's d >= 0.8, AND (3) the
    contrast survives Holm-Bonferroni. Anything else = ``"null"`` — an accepted outcome
    that licenses stripping the layer. Holm is GATING: ``holm_reject=False`` forces
    ``"null"`` even when the CI and d qualify.
    """
    if not _ci_excludes_zero(ci):
        return "null"
    if cohens_d is None or cohens_d < _LARGE_D:
        return "null"
    if not holm_reject:
        return "null"
    return "pass"


# ── Trajectory collection (cheap synth / real harness) ─────────────────────────
def _cheap_arm_trajectories(
    seed: int, trials: int, runs: int
) -> tuple[dict[str, list[list[float]]], dict[str, list[dict]]]:
    """Deterministic, LLM-free per-arm judge trajectories + per-run tax for all 5 arms.

    One seeded ``random.Random`` drives every draw sequentially (mirroring
    ``close_loop._cheap_trajectories``), so the SAME seed always yields the SAME 5-arm
    apparatus check. Both endpoints (quality trajectory + Track-2 tax) are synthesized
    so the full report format runs free.
    """
    rng = random.Random(seed)
    trajectories: dict[str, list[list[float]]] = {}
    tax: dict[str, list[dict]] = {}
    for arm in _ARMS:
        lo, hi = _CHEAP_RANGES[arm]
        trajectories[arm] = [
            [round(rng.uniform(lo, hi), 2) for _ in range(runs)] for _ in range(trials)
        ]
        tax[arm] = [
            {
                "tokens_in": rng.randint(800, 1600),
                "tokens_out": rng.randint(200, 600),
                "cache_read": rng.randint(0, 400),
                "wall_clock_s": round(rng.uniform(5.0, 30.0), 2),
            }
            for _ in range(trials * runs)
        ]
    return trajectories, tax


def _run_arm_trial(
    arm: str, runs: int, root: Path, label: str
) -> tuple[list[float] | None, list[dict]]:
    """One real harness invocation; returns (per-run judge scores, per-run tax).

    Mirrors ``replicate._run_trial``'s compound_eval subprocess call (SAME distinct
    judge/producer models — D-06 independence) but reads BOTH the ``judge.per_run``
    scores (quality endpoint) AND the ``tax`` block (Track-2) from the ``--out`` JSON,
    which ``_run_trial`` discards. Real mode only; never invoked under tests.
    """
    fd, path = tempfile.mkstemp(prefix=f"verdict_{label}_", suffix=".json")
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
        "--judge-model",
        replicate._JUDGE_MODEL,
        "--producer-model",
        replicate._PRODUCER_MODEL,
        "--out",
        str(out),
    ]
    try:
        proc = subprocess.run(cmd, check=False)
        if proc.returncode != 0:
            print(f"[verdict] {label}: compound_eval exited {proc.returncode}", flush=True)
            return None, []
        payload = json.loads(out.read_text())
    except OSError as exc:
        print(f"[verdict] {label}: no/unreadable output ({exc})", flush=True)
        return None, []
    finally:
        out.unlink(missing_ok=True)

    raw_scores = [r["score"] for r in payload.get("judge", {}).get("per_run", [])]
    scores = (
        None
        if not raw_scores or any(s is None for s in raw_scores)
        else [float(s) for s in raw_scores]
    )
    tax = payload.get("tax", {})
    per_run_tax = [
        {
            "tokens_in": tax.get("tokens_in", 0),
            "tokens_out": tax.get("tokens_out", 0),
            "cache_read": tax.get("cache_read", 0),
            "wall_clock_s": tax.get("wall_clock_s", 0.0),
        }
    ]
    return scores, per_run_tax


def _real_arm_trajectories(
    target: Path, trials: int, runs: int
) -> tuple[dict[str, list[list[float] | None]], dict[str, list[dict]]]:
    """Live per-arm judge trajectories + per-run tax via the harness. Real mode only.

    Trial identity is preserved (a failed trial stays ``None`` at its index) so the
    contrast engine can pair arm-vs-none by trial index and drop only broken pairs.
    """
    trajectories: dict[str, list[list[float] | None]] = {arm: [None] * trials for arm in _ARMS}
    tax: dict[str, list[dict]] = {arm: [] for arm in _ARMS}
    for arm in _ARMS:
        for t in range(trials):
            scores, per_run_tax = _run_arm_trial(arm, runs, target, f"{arm}{t}")
            trajectories[arm][t] = scores
            tax[arm].extend(per_run_tax)
    return trajectories, tax


def _collect(
    root: Path, mode: str, trials: int, runs: int, seed: int
) -> tuple[dict[str, list], dict[str, list[dict]], bool]:
    """Gather the 5-arm trajectories + tax. Returns (trajectories, tax, synthetic).

    Cheap mode synthesizes deterministically (free). Real mode runs the harness inside
    an isolated ``_worktree`` copy of ``root`` (D-01: the real repo is never mutated),
    scaffolding baseline memory and provisioning the producer arms first.
    """
    if mode == "cheap":
        trajectories, tax = _cheap_arm_trajectories(seed, trials, runs)
        return trajectories, tax, True

    with _worktree(root) as target:
        scaffold(target)
        for arm in _PRODUCER_ARMS:
            prepare_fixture.main(["--root", str(target), "--arms", arm])
        trajectories, tax = _real_arm_trajectories(target, trials, runs)
    return trajectories, tax, False


# ── The 4-contrast engine (reusing every existing statistic) ───────────────────
def _compute_contrasts(trajectories: dict[str, list], seed: int) -> list[dict]:
    """The 4 treatment-vs-none contrasts, each judged against the D-02 three-part gate.

    Reuses ``replicate._per_trial_improvements`` (trial-index pairing),
    ``bootstrap.paired_bootstrap_ci`` / ``paired_bootstrap_p`` (same seeded resampler),
    and ``replicate._cohens_d`` over ``replicate._agg`` dicts — NO reimplemented
    statistics. Holm-Bonferroni across the 4 raw p-values gates the pass/null label.
    """
    none_trials = trajectories["none"]
    none_present = [t for t in none_trials if t is not None]
    none_agg = replicate._agg(none_present)
    none_impr = replicate._per_trial_improvements(none_trials)

    raw: list[dict] = []
    for arm in _TREATMENTS:
        arm_trials = trajectories[arm]
        arm_present = [t for t in arm_trials if t is not None]
        arm_agg = replicate._agg(arm_present)
        arm_impr = replicate._per_trial_improvements(arm_trials)
        k = min(len(arm_impr), len(none_impr))
        deltas = [
            arm_impr[t] - none_impr[t]
            for t in range(k)
            if arm_impr[t] is not None and none_impr[t] is not None
        ]
        raw.append(
            {
                "arm": arm,
                "n_pairs": len(deltas),
                "ci": paired_bootstrap_ci(deltas, seed=seed),
                "raw_p": paired_bootstrap_p(deltas, seed=seed),
                "cohens_d": replicate._cohens_d(arm_agg, none_agg),
            }
        )

    holm = holm_bonferroni([c["raw_p"] for c in raw])
    contrasts: list[dict] = []
    for c, h in zip(raw, holm, strict=True):
        contrasts.append(
            {
                "contrast": f"{c['arm']} - none",
                "arm": c["arm"],
                "n_pairs": c["n_pairs"],
                "ci": c["ci"],
                "ci_excludes_zero": _ci_excludes_zero(c["ci"]),
                "cohens_d": c["cohens_d"],
                "raw_p": h["raw_p"],
                "holm_p": h["holm_p"],
                "holm_reject": h["reject"],
                "verdict": _gate(c["ci"], cohens_d=c["cohens_d"], holm_reject=h["reject"]),
            }
        )
    return contrasts


# ── Per-arm endpoints (quality / tax / compounding curve) ──────────────────────
def _arm_quality(trajectories: dict[str, list], arm: str) -> dict:
    """Per-arm quality via ``judge.aggregate_judges`` over that arm's per-run scores.

    Reuses the Phase-20 independent multi-judge aggregator; judge!=producer independence
    is inherited from ``replicate``'s distinct models on the real path.
    """
    present = [t for t in trajectories[arm] if t is not None]
    scores = [s for traj in present for s in traj]
    results = [JudgeResult(run_index=i, score=s, rationale="") for i, s in enumerate(scores)]
    return aggregate_judges(results)


def _arm_curve(trajectories: dict[str, list], arm: str) -> dict:
    """Per-arm compounding curve run 1->N, paired-normalized to run-0 (D-07).

    Reuses ``replicate._paired_normalize`` + ``replicate._agg``; the ``per_run_mean`` of
    the normalized aggregate is the curve. wiki/memory value, if any, is expected only at
    run 2+ (run 1 has empty memory) — a flat run-1 delta is the expected shape.
    """
    present = [t for t in trajectories[arm] if t is not None]
    if not present:
        return {"n": 0}
    return replicate._agg(replicate._paired_normalize(present))


def _arm_tax(per_run_tax: list[dict]) -> dict:
    """Per-arm Track-2 tax totals via ``report._tax_totals`` (EXCLUDED from any score).

    Wraps the per-run tax dicts in ``RunSnapshot``s so the existing ``report._tax_totals``
    summation is reused verbatim — the verdict adds no tax math of its own.
    """
    snaps = [
        RunSnapshot(
            run_index=i,
            run_id=f"r{i}",
            artifacts_changed=0,
            new_gotchas=0,
            reencountered_gotchas=0,
            verify_pass=0,
            verify_fail=0,
            verify_skip=0,
            prefix_tokens=0,
            mem_hits=0,
            layers_present=(),
            tokens_in=int(d.get("tokens_in", 0)),
            tokens_out=int(d.get("tokens_out", 0)),
            cache_read=int(d.get("cache_read", 0)),
            wall_clock_s=float(d.get("wall_clock_s") or 0.0),
        )
        for i, d in enumerate(per_run_tax)
    ]
    return report._tax_totals(SimpleNamespace(snapshots=snaps))


def build_result(
    trajectories: dict[str, list],
    tax: dict[str, list[dict]],
    *,
    synthetic: bool,
    mode: str,
    seed: int,
    trials: int,
    runs: int,
) -> dict:
    """Assemble the full verdict payload: per-arm endpoints + the 4-contrast decision."""
    contrasts = _compute_contrasts(trajectories, seed)
    arms = {
        arm: {
            "quality": _arm_quality(trajectories, arm),
            "tax": _arm_tax(tax.get(arm, [])),
            "compounding_curve": _arm_curve(trajectories, arm),
        }
        for arm in _ARMS
    }
    return {
        "mode": mode,
        "synthetic": synthetic,
        "seed": seed,
        "trials": trials,
        "runs": runs,
        "preregistration": _PREREG_DOC,
        "win_rule": (
            "D-02 three-part GATING rule: CI excludes 0 AND Cohen's d >= 0.8 AND "
            "survives Holm-Bonferroni across the 4 contrasts; else null."
        ),
        "arms": arms,
        "contrasts": contrasts,
    }


# ── Pristine-worktree control (D-01a) ──────────────────────────────────────────
# FlowState/GSD state whose presence would mean the subject repo is contaminated
# (self-reading confound) OR that run-1-empty-memory does not hold. The project's own
# .claude/ config is legitimate project content and is deliberately NOT a marker.
_STRAY_MARKERS = (
    "memory.db",
    "flowstate.json",
    ".planning",
    "PROJECT.md",
    "ROADMAP.md",
    "research",
)


def assert_pristine_worktree(root: Path) -> dict:
    """D-01a contamination control: report whether ``root`` carries stray FlowState state.

    Returns ``{"pristine", "subject", "stray_markers"}``. ``pristine`` is True iff NONE
    of ``memory.db`` / ``flowstate.json`` / ``.planning/`` / root ``PROJECT.md`` /
    ``ROADMAP.md`` / ``research/`` exist under ``root`` — their absence proves
    run-1-empty-memory and no self-reading confound. A bare ``.claude/`` config is
    legitimate project content and is NOT flagged. The result is RETURNED (not just
    raised) so the writer can embed the D-01a evidence into 22-VERDICT.md. Never raises.
    """
    root = Path(root)
    found: list[str] = []
    for marker in _STRAY_MARKERS:
        try:
            if (root / marker).exists():
                found.append(marker)
        except OSError:
            continue
    return {"pristine": not found, "subject": str(root), "stray_markers": found}


# ── 22-VERDICT.md writer (D-01a / D-02 / D-03 / D-06 / D-07) ────────────────────
def _fmt(value: object) -> str:
    """Render a scalar for a markdown cell; ``None`` -> ``n/a``."""
    return "n/a" if value is None else str(value)


def _pristine_lines(pristine: dict) -> list[str]:
    lines = ["## Pristine control (D-01a)", ""]
    if pristine["pristine"]:
        lines += [
            f"- PASS — subject `{pristine['subject']}` carries no stray FlowState state "
            "(no memory.db / flowstate.json / .planning / root PROJECT.md / ROADMAP.md / research).",
            "- Run-1-empty-memory holds by construction; no self-reading confound "
            "(the project's own `.claude/` config is legitimate, not contamination).",
        ]
    else:
        markers = ", ".join(f"`{m}`" for m in pristine["stray_markers"])
        lines += [
            f"- FAIL — subject `{pristine['subject']}` carries stray FlowState markers: {markers}.",
            "- The subject is NOT pristine; run-1-empty-memory / no-self-reading cannot be assumed.",
        ]
    return [*lines, ""]


def _arm_table_lines(result: dict) -> list[str]:
    lines = [
        "## Per-arm quality + tax + compounding curve (D-03, D-07)",
        "",
        "Quality = Phase-20 independent multi-judge mean (0-10, judge != producer). "
        "Tax is Track-2 and is EXCLUDED from any compounding score. The compounding "
        "curve is run 1->N paired-normalized to run-0 (wiki/memory value, if any, is "
        "expected only at run 2+ because run 1 has empty memory).",
        "",
        "| Arm | Quality (0-10) | tokens_in | tokens_out | cache_read | wall_clock_s | Compounding curve (norm to run-0) |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for arm in _ARMS:
        a = result["arms"][arm]
        tax = a["tax"]
        curve = a["compounding_curve"].get("per_run_mean")
        curve_str = "n/a" if not curve else " -> ".join(str(x) for x in curve)
        lines.append(
            f"| {arm} | {_fmt(a['quality']['mean'])} | {tax['tokens_in']} | "
            f"{tax['tokens_out']} | {tax['cache_read']} | {tax['wall_clock_s']:g} | {curve_str} |"
        )
    return [*lines, ""]


def _contrast_table_lines(result: dict) -> list[str]:
    lines = [
        "## The 4 co-primary contrasts — D-02 three-part GATING rule (D-06)",
        "",
        "A contrast PASSES iff its paired-bootstrap 95% CI excludes 0 AND Cohen's d >= 0.8 "
        "AND it survives Holm-Bonferroni across the 4 contrasts. Both raw and Holm-corrected "
        "significance are reported, but the WIN/null decision uses the Holm-corrected result "
        "(Holm is GATING, not decorative).",
        "",
        "| Contrast | n | CI low | CI high | excludes 0 | Cohen's d | raw p | Holm p | VERDICT |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for c in result["contrasts"]:
        ci = c["ci"]
        lines.append(
            f"| {c['contrast']} | {c['n_pairs']} | {_fmt(ci['ci_low'])} | {_fmt(ci['ci_high'])} | "
            f"{'yes' if c['ci_excludes_zero'] else 'no'} | {_fmt(c['cohens_d'])} | "
            f"{_fmt(c['raw_p'])} | {_fmt(c['holm_p'])} | **{c['verdict'].upper()}** |"
        )
    lines.append("")
    for c in result["contrasts"]:
        if c["verdict"] == "null":
            lines.append(
                f"- `{c['contrast']}` = **NULL** — an accepted, documented outcome that "
                "licenses stripping this layer (no re-running to chase significance)."
            )
    return [*lines, ""]


def render_verdict_md(result: dict, pristine: dict) -> str:
    """Render the full 22-VERDICT.md markdown from a ``build_result`` payload + pristine control."""
    mode_label = "cheap (synthetic)" if result["synthetic"] else "real"
    header = [
        "# Phase 22 — The Verdict",
        "",
        f"- Mode: **{mode_label}** · seed: {result['seed']} · trials: {result['trials']} "
        f"· runs: {result['runs']}",
        f"- Pre-registration (frozen before any real trial): `{result['preregistration']}`",
        f"- Win rule (D-02, VERBATIM): {result['win_rule']}",
        "",
    ]
    if result["synthetic"]:
        header += [
            "> SYNTHETIC cheap-mode run: the numbers below are a seeded apparatus check "
            "(plumbing proof), NOT a causal measurement. Only `--mode real` decides the verdict.",
            "",
        ]
    body = (
        header
        + _pristine_lines(pristine)
        + _arm_table_lines(result)
        + _contrast_table_lines(result)
    )
    return "\n".join(body) + "\n"


def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="bench.verdict",
        description=(
            "Pre-registered 4-contrast verdict: pack/memory/wiki/full vs none, "
            "Holm-gated, quality+tax+compounding-curve report."
        ),
    )
    ap.add_argument("--root", type=Path, required=True)
    ap.add_argument("--mode", choices=("cheap", "real"), default="cheap")
    ap.add_argument("--trials", type=int, default=5)
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--seed", type=int, default=_PREREG_SEED)
    ap.add_argument("--out", type=Path, default=None)
    return ap


def main(argv: list[str] | None = None) -> int:
    """Run the 5-arm sweep, apply the frozen D-02 rule, emit the verdict. Never raises.

    Fail-loud (D-08 / close_loop discipline): a ``--mode real`` run where any contrast
    measured zero paired trials exits ``_EXIT_NO_PAIRED_DATA`` rather than reporting a
    null CI as a clean result. Cheap mode always synthesizes and is exempt.
    """
    args = _build_parser().parse_args(argv)
    root = Path(args.root)

    # D-01a contamination control: check the subject BEFORE trials so its result is
    # embedded in the emitted 22-VERDICT.md (evidence must survive in the artifact).
    # A cheap filesystem check — safe to run in both modes, no spend.
    pristine = assert_pristine_worktree(root)

    # One-time repo grounding (real mode only): derive an interview from the subject
    # repo + run the repomix pack ONCE on --root, BEFORE the sweep, so the grounded
    # flowstate.json + pack are frozen and every _worktree copy inherits them via
    # scaffold(synthetic=False). Never per-trial — a per-trial LLM call would vary
    # across arms and confound the paired design. Cheap mode stays free/deterministic.
    if args.mode == "real":
        ground_from_repo(root)

    trajectories, tax, synthetic = _collect(root, args.mode, args.trials, args.runs, args.seed)
    contrasts = _compute_contrasts(trajectories, args.seed)
    if args.mode == "real" and any(c["n_pairs"] == 0 for c in contrasts):
        print("[verdict] real mode produced a contrast with no paired trials — failing loud")
        return _EXIT_NO_PAIRED_DATA

    result = build_result(
        trajectories,
        tax,
        synthetic=synthetic,
        mode=args.mode,
        seed=args.seed,
        trials=args.trials,
        runs=args.runs,
    )
    result["pristine_control"] = pristine

    # A compact verdict summary always goes to stdout; --out with a .md suffix writes the
    # full 22-VERDICT.md report, anything else writes the complete JSON payload.
    print(
        json.dumps(
            {
                "mode": result["mode"],
                "synthetic": result["synthetic"],
                "pristine_control": pristine,
                "contrasts": {c["contrast"]: c["verdict"] for c in result["contrasts"]},
            },
            indent=2,
        )
    )
    if args.out is not None:
        try:
            if str(args.out).endswith(".md"):
                Path(args.out).write_text(render_verdict_md(result, pristine))
            else:
                Path(args.out).write_text(json.dumps(result, indent=2) + "\n")
        except OSError as exc:
            print(f"[verdict] could not write --out: {exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
