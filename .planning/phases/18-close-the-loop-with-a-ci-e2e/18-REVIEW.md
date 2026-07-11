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
  critical: 1
  warning: 2
  info: 3
  total: 6
status: issues_found
---

# Phase 18: Code Review Report

**Reviewed:** 2026-07-10
**Depth:** standard
**Files Reviewed:** 7
**Status:** issues_found

## Summary

Reviewed the v0.6.2 "close the loop" harness surface: the seeded paired-bootstrap CI
(`bench/bootstrap.py`), the one-command driver (`bench/close_loop.py`), the N-trial
replication driver (`bench/replicate.py`), and their four test modules.

Track-2 isolation holds: neither `close_loop.py` nor `replicate.py` imports
`bench.metrics`/`compute_scorecard`, and the judge-derived CI is explicitly labelled
"EXCLUDED from compounding_score". The `bootstrap.py` edge-case handling (empty / n==1 /
all-equal / non-numeric / seed determinism) is sound and well-tested. `_worktree` +
`scaffold` correctly confine all writes to a temp copy, so the checked-in fixture is not
mutated (verified against `compound_eval._worktree` and `project.scaffold`). Cheap mode is
CI-safe (no live bridge/network) and the E2E smoke asserts fail-loud via
`_EXIT_PRODUCER_ABSENT`.

The dominant defect is statistical: when any trial drops (real mode), the "paired by trial
index" invariant that the entire CI/Cohen's d output rests on is silently violated, because
both drivers filter out `None` trials and then pair the survivors *positionally*. This can
corrupt the headline milestone verdict without any error surfacing. Two robustness issues
(silent exit-0 on total real-mode failure, and an fd/temp-file leak in `_run_trial`) and
three minor items follow.

## Critical Issues

### CR-01: Paired statistics mispair survivors when any trial drops (positional, not trial-index, pairing)

**File:** `bench/replicate.py:119-125,185-193` and `bench/close_loop.py:99-118`
**Issue:**
Both drivers document and depend on pairing "by trial index" (`replicate.py:182-184`
"per-trial deltas (arm_improvement_t - none_improvement_t), paired by trial index";
`close_loop.py:114` "paired by trial index"). But a trial that fails yields `None` from
`_run_trial`, and the collectors append *only non-None* results:

```python
# replicate.py:120-125
for t in range(a.trials):
    scores = _run_trial(arm, a.runs, a.root, f"{arm}{t}")
    if scores is not None:
        collected[arm].append(scores)   # index no longer == trial t
```

```python
# close_loop.py:101-107 (_real_trajectories) — same defect
if scores is not None:
    arm_trials.append(scores)
if base_scores is not None:
    baseline_trials.append(base_scores)
```

`_agg(...)["improvements"]` therefore preserves *surviving-trial order*, not trial order.
The downstream pairing then zips positionally:

```python
# replicate.py:191-192
k = min(len(arm_improvements), len(none_improvements))
paired_deltas = [arm_improvements[i] - none_improvements[i] for i in range(k)]
# close_loop.py:117-118 — identical positional zip
```

If arm trial 2 fails but the baseline trial 2 succeeds (or vice-versa), the arms desynchronize:
arm survivor `i` is paired against a baseline survivor from a *different* trial. Since these
are meant to be matched observations, the paired-bootstrap CI and (via the same
`improvements` lists) Cohen's d become statistically invalid — and nothing is logged. This
is precisely the primary output the milestone uses to decide "significant, production-viable
win vs. honestly conclude it isn't." A silently mispaired CI produces a wrong conclusion.

Cheap mode is unaffected (it never drops trials), and no test exercises the drop path
(`test_main_emits_bootstrap_ci_delta_vs_none` supplies 3-of-3 survivors per arm), so the bug
is currently invisible to the suite.

**Fix:** Preserve trial identity and pair on it. Keep per-trial slots (with `None` holes) and
drop a pair only when *either* side is missing:

```python
# replicate.py — keep trial index, don't compact
collected: dict[str, list[list[float] | None]] = {arm: [None] * a.trials for arm in a.layers}
for arm in a.layers:
    for t in range(a.trials):
        collected[arm][t] = _run_trial(arm, a.runs, a.root, f"{arm}{t}")

# pairing: only keep trials where BOTH arm and none produced a score
paired_deltas = [
    arm_imp[t] - none_imp[t]
    for t in range(a.trials)
    if arm_trials[t] is not None and none_trials[t] is not None
]
```

Apply the mirror fix in `close_loop._real_trajectories` / `_paired_deltas` (carry the trial
index so a unilateral failure drops the *pair*, not just one side). Add a regression test with
an asymmetric `None` (arm trial fails, baseline succeeds) asserting the surviving pairs stay
trial-aligned.

## Warnings

### WR-01: Real-mode total failure returns exit 0 with a null CI (not fail-loud)

**File:** `bench/close_loop.py:139-170`
**Issue:**
If every `_run_trial` returns `None` in `--mode real` (missing `claude` binary, all
subprocesses fail), `arm_trials`/`baseline_trials` are empty, `_paired_deltas` returns `[]`,
and `paired_bootstrap_ci([])` yields `{"n": 0, "mean": None, ...}`. `main` then falls through
to `return 0` and prints a JSON result with a null CI. A completely failed real run is
therefore indistinguishable from success at the exit-code level — contradicting the phase's
fail-loud discipline (which the producer-gate path honors via `_EXIT_PRODUCER_ABSENT`).
**Fix:** Treat an empty/`n==0` delta set in real mode as failure:

```python
deltas = _paired_deltas(arm_trials, baseline_trials)
if args.mode == "real" and not deltas:
    print("[close_loop] real mode produced no paired trials — failing loud")
    return 1
ci = paired_bootstrap_ci(deltas, seed=args.seed)
```

### WR-02: `tempfile.mkstemp` leaks a file descriptor (and the temp file) per trial

**File:** `bench/replicate.py:33`
**Issue:**
```python
out = Path(tempfile.mkstemp(prefix=f"repl_{label}_", suffix=".json")[1])
```
`mkstemp` opens and returns a file descriptor as element `[0]`; taking only `[1]` discards it
without closing, and the temp file is never unlinked. Over a full research run
(`trials × arms × 2` invocations via both `replicate.main` and `close_loop._real_trajectories`)
this leaks one fd and one file per trial, which can exhaust the process fd limit (EMFILE) on
long sweeps and litters the temp dir. Robustness bug, not mere style.
**Fix:** Use a named temp path that closes its fd, and clean up:

```python
fd, path = tempfile.mkstemp(prefix=f"repl_{label}_", suffix=".json")
os.close(fd)
out = Path(path)
try:
    subprocess.run(cmd, check=False)
    ...
finally:
    out.unlink(missing_ok=True)
```

## Info

### IN-01: Cheap mode reports `--arm`/`--baseline` labels its synthesized trajectories ignore

**File:** `bench/close_loop.py:78-92,154-162`
**Issue:** `_cheap_trajectories` synthesizes arm scores in `[4.0, 9.0]` and baseline in
`[3.0, 7.0]` regardless of the `--arm`/`--baseline` values, yet the emitted result echoes
`"arm": args.arm` / `"baseline": args.baseline`. A reader of the JSON could mistake the fixed
synthetic delta for a measurement of the named arms. It is documented as an "apparatus check,"
but the labels invite misreading.
**Fix:** In cheap mode, stamp the labels as synthetic (e.g. `"arm": f"{args.arm} (synthetic)"`)
or add a `"synthetic": true` flag to the cheap-mode result.

### IN-02: `paired_bootstrap_ci` does not validate `resamples`

**File:** `bench/bootstrap.py:57-70`
**Issue:** With `resamples <= 0` the resample loop produces an empty list and
`resample_means[lo_idx]` raises `IndexError`, which the broad `except` converts to a
`mean: None` result even for perfectly valid `deltas`. Not reachable via any current CLI
(`resamples` is always the 2000 default), so latent only.
**Fix:** Guard early: `resamples = max(1, resamples)` (or return the None-bounds dict with a
reason) before the loop.

### IN-03: Cohen's d uses population stdev and equal-weight pooling

**File:** `bench/replicate.py:87-93`
**Issue:** `_agg` computes `improvement_std` via `statistics.pstdev` (population, ddof=0) and
`_cohens_d` pools as `((s_on² + s_off²)/2)**0.5`, which assumes equal n. With unequal surviving
trial counts (see CR-01) the pooled SD is mis-weighted, and population SD slightly deflates the
denominator vs. the conventional sample SD (ddof=1). Minor for a directional effect-size
readout, but worth a note given the milestone leans on the number.
**Fix:** If rigor matters here, switch to sample stdev and the n-weighted pooled variance
`sqrt(((n1-1)s1² + (n2-1)s2²)/(n1+n2-2))`; otherwise document the simplification inline.

---

_Reviewed: 2026-07-10_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
