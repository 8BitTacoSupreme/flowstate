"""Deterministic cheap-mode tests for bench/verdict.py — the 4-contrast verdict driver.

NO claude, NO subprocess, NO network. Every test runs the pre-registered driver +
Holm-Bonferroni gate + bootstrap p-value + report + pristine control against
synthesized trajectories, proving the whole verdict pipeline is free to exercise.
"""

from __future__ import annotations

import json

import bench.bootstrap as bootstrap
import bench.verdict as verdict


# ── Holm-Bonferroni (D-06 — GATING correction) ────────────────────────────────
def test_holm_bonferroni_reject_pattern():
    """A clearly-significant p survives; a large p never does; ordering restored."""
    rows = verdict.holm_bonferroni([0.001, 0.04, 0.8, 0.02], alpha=0.05)
    assert [r["raw_p"] for r in rows] == [0.001, 0.04, 0.8, 0.02]
    assert rows[0]["reject"] is True  # 0.001 * 4 = 0.004 < 0.05
    assert rows[2]["reject"] is False  # 0.8 never rejects


def test_holm_bonferroni_is_monotone_in_sorted_order():
    """Holm-adjusted p is non-decreasing when the contrasts are sorted ascending by raw p."""
    rows = verdict.holm_bonferroni([0.001, 0.01, 0.02, 0.04])
    by_raw = sorted(rows, key=lambda r: r["raw_p"])
    holm_sorted = [r["holm_p"] for r in by_raw]
    assert holm_sorted == sorted(holm_sorted)


def test_holm_bonferroni_bites_kills_raw_significance():
    """A raw-significant contrast can become non-significant after Holm correction."""
    # 0.03 is raw-significant (< 0.05) but with 4 comparisons Holm inflates it.
    rows = verdict.holm_bonferroni([0.03, 0.03, 0.03, 0.03])
    assert all(r["raw_p"] < 0.05 for r in rows)
    assert all(r["reject"] is False for r in rows)  # 0.03 * 4 = 0.12 > 0.05


def test_holm_bonferroni_none_is_non_significant():
    """A None p-value (unmeasurable contrast) stays non-significant, never raises."""
    rows = verdict.holm_bonferroni([None, 0.001])
    none_row = next(r for r in rows if r["raw_p"] is None)
    assert none_row["holm_p"] is None
    assert none_row["reject"] is False


# ── paired_bootstrap_p (same seeded resampler as the locked CI) ────────────────
def test_bootstrap_p_separated_deltas_small():
    """Strongly-separated all-positive deltas -> small two-sided p."""
    p = bootstrap.paired_bootstrap_p([1.0, 1.2, 0.9, 1.1, 1.3])
    assert p is not None and p < 0.05


def test_bootstrap_p_zero_centered_large():
    """Deltas centered on zero -> large p (cannot reject)."""
    p = bootstrap.paired_bootstrap_p([-1.0, 1.0, -0.8, 0.8, -0.2, 0.2])
    assert p is not None and p > 0.2


def test_bootstrap_p_empty_is_none():
    assert bootstrap.paired_bootstrap_p([]) is None


def test_bootstrap_p_is_deterministic():
    a = bootstrap.paired_bootstrap_p([0.5, 0.7, 0.6], seed=99)
    b = bootstrap.paired_bootstrap_p([0.5, 0.7, 0.6], seed=99)
    assert a == b


def test_paired_bootstrap_ci_unchanged_regression_guard():
    """T-22-03: adding paired_bootstrap_p must not perturb the locked CI. Byte-identical."""
    fixed = [0.3, 0.5, -0.1, 0.4, 0.2]
    ci = bootstrap.paired_bootstrap_ci(fixed)
    assert ci == {
        "n": 5,
        "mean": 0.26,
        "ci_low": 0.06,
        "ci_high": 0.42,
        "resamples": 2000,
        "seed": 1729,
        "confidence": 0.95,
    }


# ── The D-02 three-part gate (CI-excludes-0 AND d>=0.8 AND Holm-reject) ─────────
def test_contrast_gate_all_three_pass():
    ci = {"ci_low": 0.5, "ci_high": 1.5}
    assert verdict._gate(ci, cohens_d=1.2, holm_reject=True) == "pass"


def test_contrast_gate_holm_false_forces_null():
    """Holm-reject=False forces 'null' even when CI excludes 0 AND d>=0.8 qualify."""
    ci = {"ci_low": 0.5, "ci_high": 1.5}
    assert verdict._gate(ci, cohens_d=1.2, holm_reject=False) == "null"


def test_contrast_gate_ci_straddles_zero_is_null():
    ci = {"ci_low": -0.1, "ci_high": 1.5}
    assert verdict._gate(ci, cohens_d=1.2, holm_reject=True) == "null"


def test_contrast_gate_small_effect_is_null():
    ci = {"ci_low": 0.5, "ci_high": 1.5}
    assert verdict._gate(ci, cohens_d=0.5, holm_reject=True) == "null"


# ── assert_pristine_worktree (D-01a contamination control) ─────────────────────
def test_pristine_passes_clean_dir(tmp_path):
    result = verdict.assert_pristine_worktree(tmp_path)
    assert result["pristine"] is True
    assert result["stray_markers"] == []
    assert result["subject"] == str(tmp_path)


def test_pristine_ignores_bare_claude_config(tmp_path):
    """The project's own .claude/ config is legitimate content, NOT contamination."""
    (tmp_path / ".claude").mkdir()
    assert verdict.assert_pristine_worktree(tmp_path)["pristine"] is True


def test_pristine_flags_flowstate_state(tmp_path):
    (tmp_path / "memory.db").write_text("")
    (tmp_path / "flowstate.json").write_text("{}")
    (tmp_path / ".planning").mkdir()
    result = verdict.assert_pristine_worktree(tmp_path)
    assert result["pristine"] is False
    for marker in ("memory.db", "flowstate.json", ".planning"):
        assert marker in result["stray_markers"]


# ── Full cheap-mode driver run (deterministic, free, no claude) ────────────────
def test_cheap_mode_emits_report_and_is_synthetic(tmp_path):
    out = tmp_path / "22-VERDICT.md"
    rc = verdict.main(
        [
            "--root",
            str(tmp_path),
            "--mode",
            "cheap",
            "--trials",
            "4",
            "--runs",
            "3",
            "--out",
            str(out),
        ]
    )
    assert rc == 0
    text = out.read_text()
    # Embedded pristine control section (tmp_path is clean -> PASS).
    assert "Pristine control (D-01a)" in text
    assert "PASS" in text
    # Report shape: Holm, per-arm tax, compounding curve, per-contrast verdict.
    assert "Holm" in text
    assert "tokens_in" in text
    assert "Compounding curve" in text
    assert "SYNTHETIC" in text  # cheap run is stamped synthetic
    assert "VERDICT" in text


def test_cheap_mode_is_byte_deterministic(tmp_path):
    out1 = tmp_path / "a.md"
    out2 = tmp_path / "b.md"
    argv = ["--root", str(tmp_path), "--mode", "cheap", "--seed", "20260711", "--out"]
    verdict.main([*argv, str(out1)])
    verdict.main([*argv, str(out2)])
    assert out1.read_bytes() == out2.read_bytes()


def test_cheap_mode_never_invokes_subprocess(tmp_path, monkeypatch):
    """Cheap mode must synthesize — a subprocess call would mean real spend leaked in."""

    def _boom(*args, **kwargs):
        raise AssertionError("cheap mode must not shell out")

    monkeypatch.setattr(verdict.subprocess, "run", _boom)
    rc = verdict.main(["--root", str(tmp_path), "--mode", "cheap", "--out", str(tmp_path / "v.md")])
    assert rc == 0


def test_cheap_mode_json_out_carries_contrasts_and_pristine(tmp_path):
    out = tmp_path / "verdict.json"
    rc = verdict.main(["--root", str(tmp_path), "--mode", "cheap", "--out", str(out)])
    assert rc == 0
    payload = json.loads(out.read_text())
    assert payload["synthetic"] is True
    assert payload["pristine_control"]["pristine"] is True
    assert len(payload["contrasts"]) == 4
    assert set(payload["arms"]) == {"none", "pack", "memory", "wiki", "full"}


# ── Fail-loud: a real-mode contrast that measured nothing exits non-zero ────────
def test_real_mode_no_paired_data_fails_loud(tmp_path, monkeypatch):
    """A real run where every contrast produced zero paired trials must exit
    _EXIT_NO_PAIRED_DATA, never report a null CI as a clean result. Monkeypatches the
    trajectory source so NO subprocess/claude is invoked."""
    empty = {arm: [None, None] for arm in verdict._ARMS}

    monkeypatch.setattr(verdict, "_collect", lambda *a, **k: (empty, {}, False))
    rc = verdict.main(["--root", str(tmp_path), "--mode", "real", "--trials", "2"])
    assert rc == verdict._EXIT_NO_PAIRED_DATA


def test_cheap_mode_synthetic_result_never_fails_loud(tmp_path, monkeypatch):
    """Cheap mode always synthesizes trials, so the fail-loud guard never trips."""
    monkeypatch.setattr(verdict.subprocess, "run", lambda *a, **k: None)
    rc = verdict.main(["--root", str(tmp_path), "--mode", "cheap", "--trials", "2"])
    assert rc == 0
