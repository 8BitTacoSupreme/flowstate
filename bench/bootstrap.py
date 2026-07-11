"""Seeded paired-bootstrap confidence interval for Track-2 judge deltas.

Track-2 only: this module is deliberately isolated from bench/metrics.py's
deterministic compounding_score and MUST NOT be imported by it. It consumes
per-trial paired deltas (arm improvement - none improvement) already computed
by bench/replicate.py and returns a percentile bootstrap CI on their mean.

Pure stdlib (random, statistics) — no new runtime dependency. Seeded via a
local ``random.Random`` instance (never the module-level ``random`` functions)
so repeated calls with the same seed are byte-identical. Never raises.
"""

from __future__ import annotations

import random
import statistics

_BOOTSTRAP_SEED = 1729
_DEFAULT_RESAMPLES = 2000


def paired_bootstrap_ci(
    deltas: list[float],
    *,
    resamples: int = _DEFAULT_RESAMPLES,
    seed: int = _BOOTSTRAP_SEED,
    confidence: float = 0.95,
) -> dict:
    """Percentile bootstrap CI on the mean of paired deltas. Never raises.

    Empty input -> {"n": 0, "mean": None, "ci_low": None, "ci_high": None, ...}.
    n==1 degenerates naturally to ci_low == ci_high == mean (every resample of
    size 1 draws the same single value). All-equal deltas degenerate to a
    zero-width CI at that value. ci_low <= mean <= ci_high always holds
    (defensively clamped).
    """
    try:
        n = len(deltas)
    except TypeError:
        n = 0

    if n == 0:
        return {
            "n": 0,
            "mean": None,
            "ci_low": None,
            "ci_high": None,
            "resamples": resamples,
            "seed": seed,
            "confidence": confidence,
        }

    try:
        mean = round(statistics.mean(deltas), 2)

        # Guard against resamples <= 0: an empty resample list makes
        # resample_means[lo_idx] raise IndexError, which the broad except below
        # would turn into a null CI even for perfectly valid deltas. Clamp so
        # the CI is always computed on at least one resample.
        resamples = max(1, resamples)

        rng = random.Random(seed)
        resample_means = []
        for _ in range(resamples):
            sample = [deltas[rng.randrange(n)] for _ in range(n)]
            resample_means.append(statistics.mean(sample))
        resample_means.sort()

        alpha = 1 - confidence
        lo_idx = round((alpha / 2) * (resamples - 1))
        hi_idx = round((1 - alpha / 2) * (resamples - 1))
        lo_idx = max(0, min(resamples - 1, lo_idx))
        hi_idx = max(0, min(resamples - 1, hi_idx))

        ci_low = round(resample_means[lo_idx], 2)
        ci_high = round(resample_means[hi_idx], 2)

        # Defensive clamp: percentile bootstrap can rarely place a rounded
        # bound just past the sample mean; the invariant must always hold.
        if ci_low > mean:
            ci_low = mean
        if ci_high < mean:
            ci_high = mean
    except Exception:
        return {
            "n": n,
            "mean": None,
            "ci_low": None,
            "ci_high": None,
            "resamples": resamples,
            "seed": seed,
            "confidence": confidence,
        }

    return {
        "n": n,
        "mean": mean,
        "ci_low": ci_low,
        "ci_high": ci_high,
        "resamples": resamples,
        "seed": seed,
        "confidence": confidence,
    }


def paired_bootstrap_p(
    deltas: list[float],
    *,
    resamples: int = _DEFAULT_RESAMPLES,
    seed: int = _BOOTSTRAP_SEED,
) -> float | None:
    """Two-sided bootstrap achieved-significance p-value on the mean of paired deltas.

    ADD-ONLY companion to ``paired_bootstrap_ci``: it reuses the IDENTICAL seeded
    ``random.Random(seed)`` resampling loop (same n-of-n draws, same
    ``statistics.mean`` per resample) so the p-value and the CI are computed on the
    same bootstrap distribution. ``paired_bootstrap_ci`` is left byte-identical — the
    Phase-18 CI is load-bearing.

    The two-sided p is ``2 * min(frac(resample_mean <= 0), frac(resample_mean >= 0))``,
    clamped to ``[0, 1]``: strongly-separated all-positive (or all-negative) deltas ->
    small p; deltas centered on 0 -> p near 1.0. Empty input -> ``None``. Never raises.
    """
    try:
        n = len(deltas)
    except TypeError:
        n = 0

    if n == 0:
        return None

    try:
        resamples = max(1, resamples)
        rng = random.Random(seed)
        resample_means = []
        for _ in range(resamples):
            sample = [deltas[rng.randrange(n)] for _ in range(n)]
            resample_means.append(statistics.mean(sample))

        frac_le = sum(1 for m in resample_means if m <= 0) / resamples
        frac_ge = sum(1 for m in resample_means if m >= 0) / resamples
        p = 2 * min(frac_le, frac_ge)
        return max(0.0, min(1.0, p))
    except Exception:
        return None
