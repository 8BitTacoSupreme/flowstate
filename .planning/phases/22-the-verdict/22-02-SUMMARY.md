---
phase: 22-the-verdict
plan: 02
status: complete
subsystem: testing
tags: [bench, statistics, holm-bonferroni, bootstrap, cohens-d, verdict, pre-registration]

# Dependency graph
requires:
  - phase: 18-paired-bootstrap
    provides: bench.bootstrap.paired_bootstrap_ci (the locked seeded paired CI)
  - phase: 20-evaluator-independence
    provides: bench.judge.aggregate_judges (independent multi-judge, judge != producer)
  - phase: 19-the-tax
    provides: bench.report._tax_totals + RunSnapshot real tax fields (Track-2)
  - phase: 22-the-verdict (Plan 01)
    provides: 22-PREREGISTRATION.md — the frozen D-02 three-part GATING win rule
provides:
  - bench/verdict.py — the pre-registered 4-contrast verdict driver (Holm-gated)
  - bench.bootstrap.paired_bootstrap_p — two-sided bootstrap p (same seeded resampler as the CI)
  - holm_bonferroni — pure-stdlib GATING step-down correction over the 4 co-primary contrasts
  - assert_pristine_worktree — D-01a contamination control, embedded into the verdict artifact
  - render_verdict_md — 22-VERDICT.md writer (per-arm quality + tax + compounding curve + PASS/NULL)
affects: [22-the-verdict Plan 03 (the gated paid --mode real run + verdict interpretation)]

# Tech tracking
tech-stack:
  added: []  # stdlib only — no new runtime deps (constraint honored)
  patterns:
    - "Orchestrate-don't-reimplement: the verdict adds ZERO new statistics, reusing bootstrap CI/p + replicate Cohen's d/improvements/agg/normalize + judge aggregate + report tax"
    - "ADD-ONLY around a locked primitive: paired_bootstrap_p reuses paired_bootstrap_ci's exact seeded random.Random loop; the CI stays byte-identical (regression-guarded)"
    - "Holm-Bonferroni as a GATING correction (not decorative): the WIN/null decision uses the Holm-corrected reject flag"
    - "Cheap-mode-provable: the whole driver + Holm + report + pristine control run deterministically with zero claude spend; tests never trigger a paid run"

key-files:
  created:
    - bench/verdict.py
    - tests/test_verdict.py
  modified:
    - bench/bootstrap.py

key-decisions:
  - "D-02 win rule implemented VERBATIM as a pure _gate(): pass iff CI-excludes-0 AND Cohen's d>=0.8 AND Holm-reject; every other contrast is null (accepted, licenses stripping the layer)"
  - "paired_bootstrap_p is ADD-ONLY in bench/bootstrap.py — same _BOOTSTRAP_SEED random.Random resampler as the CI; paired_bootstrap_ci left byte-identical (T-22-03 regression test)"
  - "Holm-Bonferroni is GATING: holm_reject=False forces null even when CI/d qualify (dedicated test)"
  - "Real mode reads BOTH judge.per_run scores AND the tax block from each compound_eval --out JSON; runs inside compound_eval._worktree so the subject repo is never mutated (D-01); inherits _EXIT_NO_PAIRED_DATA fail-loud"
  - "assert_pristine_worktree flags memory.db/flowstate.json/.planning/PROJECT.md/ROADMAP.md/research but NOT bare .claude/ (legitimate project config, D-01a); RETURNS its result for embedding in 22-VERDICT.md"

patterns-established:
  - "Pattern: monkeypatch verdict._collect to prove real-mode fail-loud without any subprocess/claude"
  - "Pattern: subprocess.run monkeypatched to raise, proving cheap mode never shells out"

requirements-completed: [VERD-02, VERD-03]

# Metrics
duration: 35min
completed: 2026-07-11
---

# Phase 22 Plan 02: The Verdict Driver Summary

**bench/verdict.py — a Holm-gated 4-contrast verdict driver that runs pack/memory/wiki/full each vs none, computes per-contrast paired-bootstrap CI + two-sided p + Cohen's d, applies the frozen D-02 three-part GATING win rule VERBATIM, and writes 22-VERDICT.md (per-arm quality + tax + compounding curve + PASS/NULL) — all provable deterministically in --mode cheap with zero claude spend, reusing every existing statistic.**

## Performance

- **Duration:** ~35 min
- **Tasks:** 3 (Task 1 TDD: RED → GREEN)
- **Files modified:** 3 (2 created, 1 modified)

## Accomplishments
- `paired_bootstrap_p` added to `bench/bootstrap.py` — a two-sided achieved-significance bootstrap p-value reusing the IDENTICAL seeded `random.Random` resampler as `paired_bootstrap_ci`; the CI is left byte-identical (regression-guarded, T-22-03).
- `holm_bonferroni` — a pure-stdlib step-down FWER correction over the 4 co-primary contrasts, monotone in sorted order, None-safe, and GATING (drives the WIN/null decision).
- The 5-arm / 4-contrast engine reuses `replicate._cohens_d` / `_per_trial_improvements` / `_agg` / `_paired_normalize` + `bootstrap.paired_bootstrap_ci/_p` + `judge.aggregate_judges` + `report._tax_totals` — **no reimplemented statistics** (grep-verified in the plan's key_links).
- `assert_pristine_worktree` (D-01a) returns a pass/fail + stray-marker report and is embedded into 22-VERDICT.md; it ignores the project's own `.claude/` config.
- `render_verdict_md` emits the full pre-registration-anchored report: per-arm quality (independent judge 0-10) + Track-2 tax + compounding curve (run 1→N normalized to run-0) + per-contrast CI/d/raw p/Holm p/VERDICT, with "accepted / licenses stripping" language on every null.
- Fail-loud inherited: `--mode real` with any zero-paired-delta contrast exits `_EXIT_NO_PAIRED_DATA`; cheap mode synthesizes and is exempt.

## Task Commits

1. **Task 1 (RED): failing tests for Holm / bootstrap_p / three-part gate** — `0baf8c3` (test)
2. **Task 1 (GREEN): paired_bootstrap_p + Holm-gated 4-contrast engine** — `08192af` (feat)
3. **Task 2: 22-VERDICT.md writer + pristine-worktree control** — `10f4846` (feat)
4. **Task 3: deterministic cheap-mode suite (pristine + fail-loud + determinism)** — `4e53878` (test)

## Files Created/Modified
- `bench/verdict.py` (created) — the 4-contrast driver, Holm gate, D-02 `_gate`, cheap/real trajectory collection, per-arm endpoints, `assert_pristine_worktree`, `render_verdict_md`, `main`.
- `bench/bootstrap.py` (modified, ADD-ONLY) — `paired_bootstrap_p`; `paired_bootstrap_ci` untouched.
- `tests/test_verdict.py` (created) — 22 deterministic cheap-mode tests; zero claude/subprocess/network.

## Decisions Made
- Implemented the D-02 win rule as a single pure `_gate(ci, cohens_d, holm_reject)` so the frozen three-part rule is byte-consistent with `22-PREREGISTRATION.md` and independently testable (the Holm-reject=False → null test proves Holm is gating).
- `paired_bootstrap_p` lives in `bench/bootstrap.py` (not verdict.py) so it shares the module's `_BOOTSTRAP_SEED` and resampler with the locked CI; verdict.py imports it.
- Cheap mode synthesizes BOTH endpoints (quality trajectory + Track-2 tax) from one seeded `random.Random` so the full report format — including tax and the compounding curve — is exercised free; the result is stamped `synthetic=True`.
- Real-mode `_run_arm_trial` mirrors `replicate._run_trial`'s subprocess call (same distinct judge/producer models) but additionally reads the tax block that `_run_trial` discards; this path is never exercised under tests (no claude spend).

## Deviations from Plan

None - plan executed exactly as written. (Statistics reuse, byte-identical CI, Holm gating, cheap-mode provability, and fail-loud were all specified and implemented as-is.)

## Issues Encountered
- The pre-commit ruff/format hooks reordered imports and reformatted a print block across a couple of commit attempts; re-staging the auto-fixed files cleared it. No logic impact.
- Running `pytest tests/test_verdict.py` in isolation trips the global `--cov-fail-under=80` gate (single-file coverage ~12%); the full suite passes at **91.28%** and `bench/verdict.py` / `bench/bootstrap.py` measure **81% / 82%** from the new tests alone (the uncovered lines are the real-mode subprocess paths, correctly never run).

## Next Phase Readiness
- VERD-02 / VERD-03 machinery is complete and cheap-mode-proven. Ready for **Plan 03**: produce the cost estimate, obtain the user greenlight (D-08), then run the full pre-registered 5×3 `--mode real` verdict against `/Users/jhogan/floxybot2` and interpret PASS/NULL per the frozen rule.
- `git diff` confirms `bench/bootstrap.py` is additions-only (the Phase-18 CI is load-bearing and untouched).

---
*Phase: 22-the-verdict*
*Completed: 2026-07-11*
