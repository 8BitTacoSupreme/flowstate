"""Unit tests for bench/replicate.py — paired normalization and arm aggregation.

These tests cover only the pure Python helpers (_paired_normalize, _agg, _cohens_d).
No subprocess / compound_eval / live LLM calls are made.
"""

from __future__ import annotations

from bench.replicate import _agg, _cohens_d, _paired_normalize


def test_paired_normalize_starts_trajectories_at_zero():
    """Each normalized trajectory must start at 0; deltas are preserved."""
    raw = [[5, 6, 7], [6, 6, 8]]
    result = _paired_normalize(raw)

    assert len(result) == 2
    # Every trajectory must start at 0
    for trajectory in result:
        assert trajectory[0] == 0.0, f"Expected trajectory to start at 0, got {trajectory}"

    # Deltas are preserved
    assert result[0] == [0, 1, 2], f"Expected [0,1,2], got {result[0]}"
    assert result[1] == [0, 0, 2], f"Expected [0,0,2], got {result[1]}"


def test_paired_normalize_single_run_trajectory():
    """A one-run trajectory normalizes to [0]."""
    result = _paired_normalize([[7.0]])
    assert result == [[0.0]]


def test_paired_normalize_empty_list():
    """Empty input returns empty list."""
    assert _paired_normalize([]) == []


def test_paired_normalize_preserves_negative_deltas():
    """Decreasing scores produce negative deltas after normalization."""
    raw = [[10.0, 8.0, 6.0]]
    result = _paired_normalize(raw)
    assert result == [[0.0, -2.0, -4.0]]


def test_agg_on_paired_vs_raw_retains_both():
    """_agg(raw) and _agg(_paired_normalize(raw)) differ on per_run_mean[0] but agree on improvement_mean."""
    raw = [[5.0, 6.0, 7.0], [5.0, 7.0, 8.0]]
    normalized = _paired_normalize(raw)

    raw_agg = _agg(raw)
    paired_agg = _agg(normalized)

    # per_run_mean[0] is nonzero for raw, zero for paired
    assert raw_agg["per_run_mean"][0] != 0.0, "raw per_run_mean[0] should be nonzero"
    assert paired_agg["per_run_mean"][0] == 0.0, "paired per_run_mean[0] must be 0"

    # improvement_mean (last - first) must be equal because subtracting run-0 from all scores
    # doesn't change the improvement (last - first is translation-invariant)
    assert raw_agg["improvement_mean"] == paired_agg["improvement_mean"], (
        "improvement_mean must be equal for raw and paired (translation-invariant)"
    )


def test_cohens_d_uses_selected_metric():
    """_cohens_d with known improvement_mean/std returns expected rounded value.

    Using on={mean=2, std=1} and off={mean=0, std=1} the pooled std is 1.0
    and d = (2-0)/1 = 2.0.
    """
    on = {
        "n": 5,
        "improvement_mean": 2.0,
        "improvement_std": 1.0,
        "improvements": [1.0, 2.0, 2.0, 2.0, 3.0],
        "per_run_mean": [0.0, 2.0],
        "per_run_std": [0.0, 1.0],
    }
    off = {
        "n": 5,
        "improvement_mean": 0.0,
        "improvement_std": 1.0,
        "improvements": [-1.0, 0.0, 0.0, 0.0, 1.0],
        "per_run_mean": [0.0, 0.0],
        "per_run_std": [0.0, 1.0],
    }
    d = _cohens_d(on, off)
    assert d is not None
    assert abs(d - 2.0) < 0.01, f"Expected d ≈ 2.0, got {d}"


def test_cohens_d_returns_none_when_insufficient_data():
    """_cohens_d returns None when either arm has fewer than 2 trials."""
    on = {"n": 1, "improvement_mean": 2.0, "improvement_std": 0.5}
    off = {"n": 5, "improvement_mean": 0.0, "improvement_std": 0.5}
    assert _cohens_d(on, off) is None

    # Both insufficient
    assert _cohens_d({"n": 0}, {"n": 1}) is None


def test_cohens_d_returns_none_when_pooled_std_is_zero():
    """_cohens_d returns None when pooled std is 0 (no variance between trials)."""
    on = {"n": 3, "improvement_mean": 1.0, "improvement_std": 0.0}
    off = {"n": 3, "improvement_mean": 0.0, "improvement_std": 0.0}
    assert _cohens_d(on, off) is None


def test_agg_empty_returns_n_zero():
    """_agg([]) returns {'n': 0}."""
    result = _agg([])
    assert result == {"n": 0}


def test_agg_single_trial():
    """_agg with one trajectory computes per_run_mean, std, and improvement."""
    result = _agg([[3.0, 5.0, 7.0]])
    assert result["n"] == 1
    assert result["per_run_mean"] == [3.0, 5.0, 7.0]
    assert result["improvement_mean"] == 4.0  # 7 - 3
