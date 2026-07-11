"""Unit tests for bench/bootstrap.py — seeded paired-bootstrap confidence interval.

Track-2 only: covers determinism, edge cases, and the ci_low <= mean <= ci_high
invariant. Pure stdlib, no subprocess / live LLM calls.
"""

from __future__ import annotations

from bench.bootstrap import _BOOTSTRAP_SEED, paired_bootstrap_ci


def test_same_seed_returns_identical_dicts():
    """Two calls with the same seed and inputs are byte-identical."""
    deltas = [1.0, -0.5, 2.0, 0.5, 1.5]
    result1 = paired_bootstrap_ci(deltas, seed=_BOOTSTRAP_SEED)
    result2 = paired_bootstrap_ci(deltas, seed=_BOOTSTRAP_SEED)
    assert result1 == result2


def test_default_seed_is_named_constant():
    """paired_bootstrap_ci with no seed kwarg uses the module's _BOOTSTRAP_SEED."""
    deltas = [1.0, -0.5, 2.0, 0.5, 1.5]
    result_default = paired_bootstrap_ci(deltas)
    result_explicit = paired_bootstrap_ci(deltas, seed=_BOOTSTRAP_SEED)
    assert result_default == result_explicit


def test_empty_input_yields_n_zero_and_none_bounds():
    result = paired_bootstrap_ci([])
    assert result["n"] == 0
    assert result["mean"] is None
    assert result["ci_low"] is None
    assert result["ci_high"] is None


def test_single_value_yields_degenerate_ci_at_mean():
    result = paired_bootstrap_ci([3.0])
    assert result["n"] == 1
    assert result["mean"] == 3.0
    assert result["ci_low"] == 3.0
    assert result["ci_high"] == 3.0


def test_all_equal_deltas_yield_zero_width_ci():
    result = paired_bootstrap_ci([2.0, 2.0, 2.0, 2.0])
    assert result["mean"] == 2.0
    assert result["ci_low"] == 2.0
    assert result["ci_high"] == 2.0


def test_ci_bounds_bracket_mean_on_mixed_sign_input():
    deltas = [-3.0, -1.0, 0.5, 2.0, 4.0, -2.0, 1.5, 3.0]
    result = paired_bootstrap_ci(deltas)
    assert result["ci_low"] <= result["mean"] <= result["ci_high"]


def test_changing_seed_changes_bounds_not_mean():
    deltas = [-3.0, -1.0, 0.5, 2.0, 4.0, -2.0, 1.5, 3.0]
    result_a = paired_bootstrap_ci(deltas, seed=1729)
    result_b = paired_bootstrap_ci(deltas, seed=99)
    assert result_a["mean"] == result_b["mean"]
    assert result_a["ci_low"] != result_b["ci_low"] or result_a["ci_high"] != result_b["ci_high"]


def test_never_raises_on_non_numeric_input():
    """Non-numeric elements must degenerate to None bounds, not raise."""
    result = paired_bootstrap_ci(["a", "b", "c"])
    assert result["n"] == 3
    assert result["mean"] is None
    assert result["ci_low"] is None
    assert result["ci_high"] is None


def test_resamples_zero_yields_valid_ci_for_nonempty_deltas():
    """IN-02: resamples=0 must not produce a null CI — the guard clamps to >=1 so
    valid deltas still get real (non-None) bounds instead of an IndexError-null."""
    result = paired_bootstrap_ci([1.0, 2.0, 3.0], resamples=0)
    assert result["n"] == 3
    assert result["mean"] == 2.0
    assert result["ci_low"] is not None
    assert result["ci_high"] is not None
    assert result["ci_low"] <= result["mean"] <= result["ci_high"]


def test_result_keys_present():
    result = paired_bootstrap_ci([1.0, 2.0, 3.0])
    for key in ("n", "mean", "ci_low", "ci_high", "resamples", "seed", "confidence"):
        assert key in result
