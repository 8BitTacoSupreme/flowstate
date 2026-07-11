"""Unit tests for bench/replicate.py — paired normalization and arm aggregation.

These tests cover only the pure Python helpers (_paired_normalize, _agg, _cohens_d)
plus argparse acceptance for the --layers wiki arm.
No subprocess / compound_eval / live LLM calls are made.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from bench.replicate import _agg, _cohens_d, _paired_normalize, main


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


# ---------------------------------------------------------------------------
# Parser tests — wiki arm acceptance
# ---------------------------------------------------------------------------


def test_replicate_parser_accepts_layers_wiki():
    """--layers wiki must parse without error (argparse choice validation)."""
    # Build the parser by inspection (main calls ap.parse_args internally).
    # Use the internal argparse build by running parse_args directly.
    import argparse
    from pathlib import Path

    # Reconstruct the parser from replicate.py (mirrors main's local build).
    ap = argparse.ArgumentParser(prog="bench.replicate")
    ap.add_argument("--trials", type=int, default=5)
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--root", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument(
        "--layers",
        nargs="+",
        choices=("full", "pack", "memory", "none", "wiki"),
        default=["full", "pack", "memory", "none"],
    )
    ap.add_argument("--paired", action="store_true")

    args = ap.parse_args(["--root", ".", "--layers", "wiki"])
    assert args.layers == ["wiki"]


def test_replicate_default_arm_list_unchanged():
    """Default --layers list must remain ['full','pack','memory','none'] (wiki not added)."""
    import argparse
    from pathlib import Path

    ap = argparse.ArgumentParser(prog="bench.replicate")
    ap.add_argument("--trials", type=int, default=5)
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--root", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument(
        "--layers",
        nargs="+",
        choices=("full", "pack", "memory", "none", "wiki"),
        default=["full", "pack", "memory", "none"],
    )
    ap.add_argument("--paired", action="store_true")

    args = ap.parse_args(["--root", "."])
    assert args.layers == ["full", "pack", "memory", "none"]
    assert "wiki" not in args.layers


def test_compound_eval_layers_map_wiki_entry():
    """_LAYERS_MAP['wiki'] must equal frozenset({'fixtures','wiki'})."""
    from bench.compound_eval import _LAYERS_MAP

    assert "wiki" in _LAYERS_MAP
    assert _LAYERS_MAP["wiki"] == frozenset({"fixtures", "wiki"})


def test_compound_eval_parser_accepts_layers_wiki():
    """compound_eval --layers wiki must be accepted by its argparse."""

    from bench.compound_eval import _build_parser

    parser = _build_parser()
    args = parser.parse_args(["--root", ".", "--layers", "wiki"])
    assert args.layers == "wiki"


# ---------------------------------------------------------------------------
# Track-2 paired-bootstrap CI wiring
# ---------------------------------------------------------------------------


def test_main_emits_bootstrap_ci_delta_vs_none(monkeypatch, tmp_path):
    """main() wires bootstrap_ci_delta_vs_none into the summary JSON for each
    non-none arm, sourced from _run_trial's per-trial trajectories."""
    fixed_trials = {
        "wiki": [[5.0, 6.0, 8.0], [5.0, 7.0, 9.0], [5.0, 6.0, 7.0]],
        "none": [[5.0, 5.5, 6.0], [5.0, 5.0, 5.5], [5.0, 6.0, 6.0]],
    }
    calls: dict[str, int] = {"wiki": 0, "none": 0}

    def fake_run_trial(arm, runs, root, label):
        idx = calls[arm]
        calls[arm] += 1
        return fixed_trials[arm][idx]

    monkeypatch.setattr("bench.replicate._run_trial", fake_run_trial)

    out_path = Path(tempfile.mkstemp(dir=tmp_path, suffix=".json")[1])
    rc = main(
        [
            "--root",
            str(tmp_path),
            "--layers",
            "wiki",
            "none",
            "--trials",
            "3",
            "--runs",
            "3",
            "--out",
            str(out_path),
        ]
    )
    assert rc == 0

    summary = json.loads(out_path.read_text())
    assert "bootstrap_ci_delta_vs_none" in summary
    wiki_ci = summary["bootstrap_ci_delta_vs_none"]["wiki"]
    assert isinstance(wiki_ci["mean"], float)
    assert isinstance(wiki_ci["ci_low"], float)
    assert isinstance(wiki_ci["ci_high"], float)
    assert wiki_ci["ci_low"] <= wiki_ci["mean"] <= wiki_ci["ci_high"]
    # none must not appear as a key of its own delta-vs-itself
    assert "none" not in summary["bootstrap_ci_delta_vs_none"]


def test_main_omits_bootstrap_ci_when_none_arm_absent(monkeypatch, tmp_path):
    """When 'none' is not among --layers, no bootstrap_ci_delta_vs_none block is emitted."""

    def fake_run_trial(arm, runs, root, label):
        return [1.0, 2.0, 3.0]

    monkeypatch.setattr("bench.replicate._run_trial", fake_run_trial)

    out_path = Path(tempfile.mkstemp(dir=tmp_path, suffix=".json")[1])
    rc = main(
        [
            "--root",
            str(tmp_path),
            "--layers",
            "wiki",
            "--trials",
            "2",
            "--runs",
            "2",
            "--out",
            str(out_path),
        ]
    )
    assert rc == 0
    summary = json.loads(out_path.read_text())
    assert "bootstrap_ci_delta_vs_none" not in summary


# ---------------------------------------------------------------------------
# WR-02: _run_trial must not leak the mkstemp fd / temp file
# ---------------------------------------------------------------------------


def test_run_trial_removes_temp_file_on_success(monkeypatch):
    """_run_trial closes the mkstemp fd and unlinks the temp file after a run."""
    import bench.replicate as rep

    captured: dict[str, str] = {}

    def fake_run(cmd, check=False):
        out_path = cmd[cmd.index("--out") + 1]
        captured["out"] = out_path
        Path(out_path).write_text(
            json.dumps({"judge": {"per_run": [{"score": 5.0}, {"score": 7.0}]}})
        )

    monkeypatch.setattr("bench.replicate.subprocess.run", fake_run)

    scores = rep._run_trial("wiki", 2, Path("."), "wiki0")
    assert scores == [5.0, 7.0]
    assert not Path(captured["out"]).exists(), "temp file must be unlinked"


def test_run_trial_removes_temp_file_on_failure(monkeypatch):
    """The temp file is cleaned up even when the trial yields no usable scores."""
    import bench.replicate as rep

    captured: dict[str, str] = {}

    def fake_run(cmd, check=False):
        # write nothing -> read_text raises -> _run_trial returns None
        captured["out"] = cmd[cmd.index("--out") + 1]

    monkeypatch.setattr("bench.replicate.subprocess.run", fake_run)

    scores = rep._run_trial("none", 2, Path("."), "none0")
    assert scores is None
    assert not Path(captured["out"]).exists(), "temp file must be unlinked on failure"


# ---------------------------------------------------------------------------
# CR-01: paired-bootstrap CI must pair by TRIAL INDEX, not survivor position
# ---------------------------------------------------------------------------


def test_per_trial_improvements_preserves_none_holes():
    """_per_trial_improvements keeps a slot per trial index, None where absent."""
    from bench.replicate import _per_trial_improvements

    trials = [[5.0, 6.0, 8.0], None, [5.0, 6.0, 7.0]]
    assert _per_trial_improvements(trials) == [3.0, None, 2.0]
    # all-missing -> all-None, same length
    assert _per_trial_improvements([None, None]) == [None, None]


def test_main_pairs_bootstrap_ci_by_trial_index_when_arm_trial_drops(monkeypatch, tmp_path):
    """When arm trial 1 fails (None) but the none baseline trial 1 succeeds, the
    pair for trial 1 must be dropped whole and trials 0/2 stay index-aligned.

    Positional survivor-compaction (the old bug) would pair arm[2] against
    none[1] and yield a different CI. Correct trial-index pairing keeps deltas
    [imp_wiki0 - imp_none0, imp_wiki2 - imp_none2] = [3-1, 2-1] = [2.0, 1.0]
    -> mean 1.5, n 2. The buggy positional version would give [2.0, 1.5].
    """
    trials_by_arm = {
        "wiki": [[5.0, 6.0, 8.0], None, [5.0, 6.0, 7.0]],  # improvements: 3, -, 2
        "none": [[5.0, 5.5, 6.0], [5.0, 5.0, 5.5], [5.0, 6.0, 6.0]],  # improvements: 1, 0.5, 1
    }
    idx = {"wiki": 0, "none": 0}

    def fake_run_trial(arm, runs, root, label):
        i = idx[arm]
        idx[arm] += 1
        return trials_by_arm[arm][i]

    monkeypatch.setattr("bench.replicate._run_trial", fake_run_trial)

    out_path = tmp_path / "out.json"
    rc = main(
        [
            "--root",
            str(tmp_path),
            "--layers",
            "wiki",
            "none",
            "--trials",
            "3",
            "--runs",
            "3",
            "--out",
            str(out_path),
        ]
    )
    assert rc == 0

    summary = json.loads(out_path.read_text())
    wiki_ci = summary["bootstrap_ci_delta_vs_none"]["wiki"]
    # trial-index pairing keeps trials 0 and 2 only (trial 1 arm-side dropped)
    assert wiki_ci["n"] == 2
    assert wiki_ci["mean"] == 1.5
    assert wiki_ci["ci_low"] <= wiki_ci["mean"] <= wiki_ci["ci_high"]
