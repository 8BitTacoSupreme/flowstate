"""Pure metrics core for the intrinsic compounding harness — no IO, never raises.

Turns a sequence of per-run ``RunSnapshot``s into a 4-axis verdict. Each axis is
one of ``compounding`` / ``flat`` / ``regressing`` / ``insufficient-data``; the
headline ``CompoundingScore`` is ``(#compounding) - (#regressing)`` clamped to
``[-4, +4]``. A run is judged ``compounding`` only when the score is strong AND
enrichment (the mechanism) fires AND nothing regressed.

An axis reads ``insufficient-data`` when there is no underlying signal to measure
across the run sequence (e.g. verify is all-skip every run, or ``artifacts_changed``
is absent every run). ``insufficient-data`` is distinct from ``flat``: a flat axis
WAS measured and did not move, whereas an insufficient-data axis could not be
measured at all. An ``insufficient-data`` axis contributes nothing toward a positive
compounding verdict (it is neither a +1 compounding nor a -1 regression).

These functions are deliberately deterministic and dependency-free (stdlib only).
Trend detection is a simple first-vs-last comparison with a tolerance band so that
flat noise does not register as a trend.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import pairwise
from typing import Literal

# Each axis verdict is one of these four labels.
AxisVerdict = Literal["compounding", "flat", "regressing", "insufficient-data"]
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
    # Real per-run consumption (Plan 19-02): sourced from the pipeline bridge usage
    # totals via the RUN journal entry. Pure carriage — no axis reads these; they are
    # appended with defaults so all existing construction sites stay valid. Distinct
    # from prefix_tokens, which measures input-context SIZE (a Track-1 growth signal).
    tokens_in: int = 0
    tokens_out: int = 0
    cache_read: int = 0
    wall_clock_s: float | None = None


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
    Fewer than two runs is insufficient data => flat. If ``artifacts_changed``
    is zero on every run there is no convergence signal to read at all, which is
    reported as ``insufficient-data`` (distinct from a measured-but-flat axis).
    """
    if len(snapshots) < 2:
        return "flat"
    if all(s.artifacts_changed == 0 for s in snapshots):
        return "insufficient-data"
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
    # All-skip on every run => the verify axis was never actually exercised; there
    # is no pass/fail movement to read. Report insufficient-data, not flat.
    if all(s.verify_pass == 0 and s.verify_fail == 0 for s in snapshots):
        return "insufficient-data"
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
    ``insufficient-data`` axes count toward NEITHER term — an axis with no
    underlying signal cannot push the verdict positive or negative.

    verdict == "compounding" iff score >= +2 AND enrichment == compounding AND no
    axis == regressing (an insufficient-data enrichment axis can never satisfy the
    enrichment requirement). A genuine regression is surfaced as "regressing"
    even when the net score nets to 0, so one regressing axis is never masked by
    compounding ones. Empty / single-snapshot inputs yield all-flat, score 0.
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
    if has_regression and score < 2:
        # Surface a real regression even when the net score is 0 (LOW-02): a
        # single regressing axis must not be masked by compounding ones.
        verdict: Verdict = "regressing"
    elif score >= 2 and enrich == "compounding" and not has_regression:
        verdict = "compounding"
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
