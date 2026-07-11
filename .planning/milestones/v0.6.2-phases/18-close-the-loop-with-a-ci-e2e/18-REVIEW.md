---
phase: 18-close-the-loop-with-a-ci-e2e
reviewed: 2026-07-10T00:00:00Z
depth: standard
files_reviewed: 7
files_reviewed_list:
  - bench/bootstrap.py
  - bench/close_loop.py
  - bench/replicate.py
  - tests/test_bench_bootstrap.py
  - tests/test_bench_close_loop.py
  - tests/test_bench_e2e_smoke.py
  - tests/test_bench_replicate.py
findings:
  critical: 0
  warning: 0
  info: 0
  total: 0
status: clean
info_resolved: 3
resolved_commits: [30834fb, 2791939, c56968a]
---

# Phase 18: Code Review Report (Re-Review)

**Reviewed:** 2026-07-10 (info items resolved 2026-07-11 via `/gsd-code-review 18 --fix --all`)
**Depth:** standard
**Files Reviewed:** 7
**Status:** clean — CR-01 / WR-01 / WR-02 resolved earlier; all 3 info items now fixed (IN-01 `30834fb`, IN-02 `2791939`, IN-03 `c56968a`); suite 1110 passed @ 90%

## Summary

Re-review after fixes to the prior BLOCKER (CR-01) and two WARNINGs (WR-01, WR-02). All
three are **genuinely resolved** — verified by tracing the data flow, not just by trusting
the tests — and no new defects were introduced. Track-2 isolation still holds. The four
test modules (39 tests) pass under `uv run pytest`.

### CR-01 — paired statistics mispair when trials drop: RESOLVED (statistically correct)

Both drivers now route through the shared, None-preserving, trial-index-aligned helper
`bench.replicate._per_trial_improvements` (replicate.py:95-108):

- The helper returns exactly one slot per input trial index, `None` where a trial is absent,
  and computes `t[k-1] - t[0]` per trajectory. `k = min(len(t) for t in present)` guards
  ragged run counts within an arm (consistent with `_agg`). All-missing input returns
  `[None] * len(trials)` with the correct length (replicate.py:104-108). Improvement is
  translation-invariant, so raw and paired-normalized inputs give identical per-trial values.
- `close_loop._paired_deltas` (close_loop.py:127-134) runs both sides through the helper and
  keeps a pair only when `arm_improvements[t] is not None AND baseline_improvements[t] is not
  None` — asymmetric `None` holes are handled on **both** sides. `arm_i` pairs with
  `baseline_i` for the SAME original trial index: `_real_trajectories` (close_loop.py:110-115)
  appends one slot per `t in range(trials)` on both sides, so both lists are length `trials`
  and `k = min(...) = trials`; no positional compaction remains.
- `replicate.main` (replicate.py:216-227) applies the identical index-aligned pairing against
  `collected["none"]`, iterating `range(a.trials)` over lists initialized to `[None] *
  a.trials` — indexing is in-bounds by construction, and the `collected` dict now keeps
  `None` holes instead of `append`-compacting survivors.
- The two discriminating regression tests
  (`test_real_mode_pairs_by_trial_index_when_arm_trial_drops`,
  `test_main_pairs_bootstrap_ci_by_trial_index_when_arm_trial_drops`) encode the exact case
  the old bug got wrong: arm=[3,None,2] vs base=[1,0.5,1] → correct deltas [2.0,1.0] (n=2,
  mean 1.5), where positional compaction would have produced [2.0,1.5]. Both pass.

### WR-01 — real-mode total failure returned exit 0 + null CI: RESOLVED

`close_loop.py:47` defines `_EXIT_NO_PAIRED_DATA = 4`; `close_loop.py:169-171` returns it when
`args.mode == "real" and not deltas`. The `return` fires **before** the result dict is built
or `--out` is written, so no result file is emitted on the fail-loud path (asserted by
`test_real_mode_all_trials_fail_exits_nonzero`: `rc != 0` and `not out.exists()`). Cheap mode
is correctly exempt — it always synthesizes non-empty trajectories, so the guard cannot trip
on a legitimate cheap run.

### WR-02 — fd + temp-file leak in `_run_trial`: RESOLVED

`replicate.py:37-64`: the `mkstemp` fd is closed immediately (`os.close(fd)`, line 38) and the
temp file is unlinked in a `finally: out.unlink(missing_ok=True)` (lines 63-64) that runs on
both the success path and the `except -> return None` path. `os` is imported and used; no new
unused imports. Covered by `test_run_trial_removes_temp_file_on_success` and `..._on_failure`.

### Track-2 isolation — HOLDS

`bench/metrics.py` imports none of `bootstrap`/`replicate`/`close_loop`, and none of those
three import `bench.metrics`. The "EXCLUDED from compounding_score" note remains accurate; the
fixes added no dependency edge into the deterministic scorecard.

## Narrative Findings (AI reviewer)

No blocker or warning findings remain. The three info items below were resolved on
2026-07-11 via `/gsd-code-review 18 --fix --all` (commits IN-01 `30834fb`, IN-02 `2791939`,
IN-03 `c56968a`); full suite 1110 passed @ 90%, Track-2 isolation and the CR-01/WR-01/WR-02
and `_run_trial` contracts preserved. Retained below for the record.

## Info (all resolved 2026-07-11)

### IN-01: Cheap mode echoes `--arm`/`--baseline` labels its synthesized trajectories ignore

**File:** `bench/close_loop.py:84-98,177-185`
**Issue:** `_cheap_trajectories` synthesizes arm scores in `[4.0, 9.0]` and baseline in
`[3.0, 7.0]` regardless of the `--arm`/`--baseline` values, yet the emitted result echoes
`"arm": args.arm` / `"baseline": args.baseline`. A reader of the JSON could mistake the fixed
synthetic delta for a measurement of the named arms. Documented as an "apparatus check," but
the labels still invite misreading.
**Fix:** In cheap mode, stamp the labels as synthetic (e.g. `f"{args.arm} (synthetic)"`) or add
a `"synthetic": true` flag to the cheap-mode result. **RESOLVED `30834fb`** — added `"synthetic": args.mode == "cheap"` to the result dict (True cheap, False real); payload shape unchanged.

### IN-02: `paired_bootstrap_ci` does not validate `resamples`

**File:** `bench/bootstrap.py:57-70`
**Issue:** With `resamples <= 0` the resample loop produces an empty list and
`resample_means[lo_idx]` raises `IndexError`, which the broad `except` converts to a
`mean: None` result even for valid `deltas`. Not reachable via any current CLI (`resamples`
defaults to 2000), so latent only. Related latent edge: `close_loop --mode cheap --trials 0`
yields an empty-delta null CI at exit 0 (cheap mode is deliberately outside the WR-01 guard).
**Fix:** Guard early: `resamples = max(1, resamples)` (or return the None-bounds dict) before
the loop. **RESOLVED `2791939`** — `resamples = max(1, resamples)` guard before the resample loop; `resamples=0` now yields a valid CI.

### IN-03: Cohen's d uses population stdev and equal-weight pooling

**File:** `bench/replicate.py:87-93,111-117`
**Issue:** `_agg` computes `improvement_std` via `statistics.pstdev` (population, ddof=0) and
`_cohens_d` pools as `((s_on**2 + s_off**2)/2)**0.5`, which assumes equal n. With unequal
surviving-trial counts the pooled SD is mis-weighted, and population SD slightly deflates the
denominator vs. the conventional sample SD (ddof=1). Minor for a directional effect-size
readout, but worth a note given the milestone leans on the number.
**Fix:** Switch to sample stdev and the n-weighted pooled variance
`sqrt(((n1-1)s1**2 + (n2-1)s2**2)/(n1+n2-2))`, or document the simplification inline.
**RESOLVED `c56968a`** — chose the inline-documentation option: a sample-stdev switch
(`statistics.stdev`) raises on legitimate n=1 trials, so `_agg`/`_cohens_d` now carry an inline
note explaining the ddof=0 / equal-weight-pooling assumption; zero numeric change, never-raises preserved.

---

_Reviewed: 2026-07-10_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
