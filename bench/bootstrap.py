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
