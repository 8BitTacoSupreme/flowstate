"""Pure metrics core for the intrinsic compounding harness — no IO, never raises.

Turns a sequence of per-run ``RunSnapshot``s into a 4-axis verdict. Each axis is
one of ``compounding`` / ``flat`` / ``regressing``; the headline ``CompoundingScore``
is ``(#compounding) - (#regressing)`` clamped to ``[-4, +4]``. A run is judged
``compounding`` only when the score is strong AND enrichment (the mechanism) fires
AND nothing regressed.

These functions are deliberately deterministic and dependency-free (stdlib only).
Trend detection is a simple first-vs-last comparison with a tolerance band so that
flat noise does not register as a trend.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import pairwise
from typing import Literal

# Each axis verdict is one of these three labels.
AxisVerdict = Literal["compounding", "flat", "regressing"]
Verdict = Literal["compounding", "flat", "regressing"]

# Number of measured axes; the score is clamped to ±this value.
_AXIS_COUNT = 4

# Relative tolerance band: a first-vs-last change smaller than this fraction of the
# baseline is treated as noise (flat) rather than a real trend.
_TOLERANCE = 0.10


@dataclass(frozen=True)
class RunSnapshot:
    """Per-run signals the axes consume. Built by ``bench.capture``; pure data here."""

    run_index: int
    run_id: str
    artifacts_changed: int
    new_gotchas: int
    reencountered_gotchas: int
    verify_pass: int
    verify_fail: int
    verify_skip: int
    prefix_tokens: int
    mem_hits: int
    layers_present: tuple[str, ...]


@dataclass(frozen=True)
class Scorecard:
    """The 4-axis verdict plus the headline score, overall verdict, and inputs."""

    axis_convergence: AxisVerdict
    axis_gotcha_learning: AxisVerdict
    axis_verify_non_regression: AxisVerdict
    axis_enrichment: AxisVerdict
    compounding_score: int
    verdict: Verdict
    snapshots: tuple[RunSnapshot, ...] = field(default_factory=tuple)


def _trend_down(first: float, last: float) -> AxisVerdict:
    """Classify a metric that is GOOD when it decreases (first -> last)."""
    band = abs(first) * _TOLERANCE
    if last < first - band:
        return "compounding"
    if last > first + band:
        return "regressing"
    return "flat"


def _trend_up(first: float, last: float) -> AxisVerdict:
    """Classify a metric that is GOOD when it increases (first -> last)."""
    band = abs(first) * _TOLERANCE
    if last > first + band:
        return "compounding"
    if last < first - band:
        return "regressing"
    return "flat"


def axis_convergence(snapshots: list[RunSnapshot]) -> AxisVerdict:
    """Work stops repeating: ``artifacts_changed`` trends down toward a floor.

    Falling deltas => compounding; rising => regressing; steady => flat.
    Fewer than two runs is insufficient data => flat.
    """
    if len(snapshots) < 2:
        return "flat"
    return _trend_down(snapshots[0].artifacts_changed, snapshots[-1].artifacts_changed)


def axis_gotcha_learning(snapshots: list[RunSnapshot]) -> AxisVerdict:
    """Failures recur recognized, not novel: ``new_gotchas`` decays over runs.

    Decaying new-gotcha count => compounding; rising => regressing; steady => flat.
    """
    if len(snapshots) < 2:
        return "flat"
    return _trend_down(snapshots[0].new_gotchas, snapshots[-1].new_gotchas)


def axis_verify_non_regression(snapshots: list[RunSnapshot]) -> AxisVerdict:
    """Verify gates never regress: pass count never drops, fail count never rises.

    Any later run with more fails or fewer passes than an earlier run => regressing.
    Otherwise improvement (more passes or fewer fails end-to-end) => compounding;
    perfectly steady => flat.
    """
    if len(snapshots) < 2:
        return "flat"
    # Scan adjacent pairs for any genuine regression first.
    for prev, cur in pairwise(snapshots):
        if cur.verify_fail > prev.verify_fail or cur.verify_pass < prev.verify_pass:
            return "regressing"
    first, last = snapshots[0], snapshots[-1]
    improved = last.verify_pass > first.verify_pass or last.verify_fail < first.verify_fail
    return "compounding" if improved else "flat"


def axis_enrichment(snapshots: list[RunSnapshot]) -> AxisVerdict:
    """The mechanism: the assembled prefix grows (more tokens, hits, and layers).

    Combines prefix_tokens, mem_hits, and layer count into a single growth signal.
    Growth => compounding; shrink => regressing; steady => flat.
    """
    if len(snapshots) < 2:
        return "flat"
    first, last = snapshots[0], snapshots[-1]
    first_score = first.prefix_tokens + first.mem_hits + len(first.layers_present)
    last_score = last.prefix_tokens + last.mem_hits + len(last.layers_present)
    return _trend_up(first_score, last_score)


def compute_scorecard(snapshots: list[RunSnapshot]) -> Scorecard:
    """Compute the four axes, the headline score, and the overall verdict. Never raises.

    CompoundingScore = (#compounding) - (#regressing), clamped to [-4, +4].
    verdict == "compounding" iff score >= +2 AND enrichment == compounding AND no
    axis == regressing. Empty / single-snapshot inputs yield all-flat, score 0.
    """
    seq = list(snapshots)
    conv = axis_convergence(seq)
    gotcha = axis_gotcha_learning(seq)
    verify = axis_verify_non_regression(seq)
    enrich = axis_enrichment(seq)

    axes = (conv, gotcha, verify, enrich)
    raw = sum(1 for a in axes if a == "compounding") - sum(1 for a in axes if a == "regressing")
    score = max(-_AXIS_COUNT, min(_AXIS_COUNT, raw))

    has_regression = any(a == "regressing" for a in axes)
    if score >= 2 and enrich == "compounding" and not has_regression:
        verdict: Verdict = "compounding"
    elif score < 0:
        verdict = "regressing"
    else:
        verdict = "flat"

    return Scorecard(
        axis_convergence=conv,
        axis_gotcha_learning=gotcha,
        axis_verify_non_regression=verify,
        axis_enrichment=enrich,
        compounding_score=score,
        verdict=verdict,
        snapshots=tuple(seq),
    )
