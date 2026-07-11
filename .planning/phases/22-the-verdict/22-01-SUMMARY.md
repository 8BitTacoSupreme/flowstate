---
phase: 22-the-verdict
plan: 01
subsystem: benchmark
status: complete
tags: [pre-registration, verdict, measurement-protocol, VERD-01]
requires: []
provides:
  - "22-PREREGISTRATION.md — frozen, committed measurement protocol (VERD-01)"
  - "The three-part gating win rule that bench/verdict.py (Plan 02) must implement verbatim"
affects:
  - "22-02 (bench/verdict.py must be byte-consistent with this doc)"
  - "22-03 (the real run is gated on this commit preceding it — D-04)"
tech-stack:
  added: []
  patterns: [pre-registration-before-data, commit-before-run-ordering]
key-files:
  created:
    - .planning/phases/22-the-verdict/22-PREREGISTRATION.md
  modified: []
decisions:
  - "Pinned seed = 20260711 (the write date) for reproducibility (D-08 discretion)"
  - "Transcribed D-01..D-08 verbatim into a standalone frozen doc; did not re-decide any rule"
metrics:
  duration: ~2 min
  completed: 2026-07-11
---

# Phase 22 Plan 01: Pre-Register the Verdict Protocol Summary

Wrote and committed `22-PREREGISTRATION.md` — the frozen, scientific pre-registration for the
Phase 22 verdict — before any `--mode real` trial, establishing the commit-before-data integrity
anchor (D-04) that VERD-01 requires.

## What Was Built

A standalone `22-PREREGISTRATION.md` transcribing the locked CONTEXT decisions D-01..D-08 into a
frozen protocol document with a "do not amend after first real trial" banner. Sections, each
citing its D-ID:

1. **Subject repo (D-01/D-01a):** `/Users/jhogan/floxybot2` — pristine of FlowState artifacts,
   never authored by FlowState (resolves the `bride_of_flinkenstein` self-reading confound);
   isolated-worktree / never-mutate discipline; run-1-empty-memory naturally satisfied.
2. **Win rule (D-02):** the frozen COMBINED three-part GATING rule — an arm WINS iff ALL THREE:
   (1) paired-bootstrap 95% CI excludes 0, (2) Cohen's d ≥ 0.8, (3) survives Holm-Bonferroni
   (gating). Anything else = null-and-accepted; no re-running to chase significance.
3. **Endpoints (D-03):** quality = Phase-20 independent multi-judge; tax = Phase-19 tokens +
   wall-clock (Track-2, excluded from compounding_score); reported side by side.
4. **Arms/contrasts (D-05):** 5 arms (none·pack·memory·wiki·full); 4 co-primary treatment−none
   contrasts.
5. **Correction (D-06):** Holm-Bonferroni is GATING; both raw and Holm-corrected reported, WIN/null
   uses the corrected result.
6. **Compounding curve (D-07):** run 1→3 per arm, paired-normalized to run-0; wiki/memory value
   only at run 2+.
7. **Sample size/cost (D-08):** n = trials 5, runs 3, --mode real, seed 20260711; cheap check →
   cost estimate + user greenlight → full 5×3.
8. **Frozen banner** with write date.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Write and commit 22-PREREGISTRATION.md | a1f09aa | .planning/phases/22-the-verdict/22-PREREGISTRATION.md |

## Byte-Consistency Note (forward dependency)

`bench/verdict.py` does not yet exist — it is built in Plan 02. This document is the frozen
spec that verdict.py must implement VERBATIM: the three-part gate (CI-excludes-0 AND d≥0.8 AND
survives-Holm), with the Holm-corrected result deciding WIN/null. The acceptance criterion
"byte-consistent with bench/verdict.py" is a constraint on Plan 02, satisfiable because
verdict.py had not yet been authored when the rule was frozen here.

## Deviations from Plan

None — plan executed exactly as written. Seed value (left to executor discretion per D-08) was
pinned to 20260711.

## Self-Check: PASSED

- FOUND: .planning/phases/22-the-verdict/22-PREREGISTRATION.md
- FOUND: commit a1f09aa (git log for the path returns a commit)
- Automated verify: `test -f` && grep Cohen && grep Holm && grep -i gating && git log → ALL_VERIFY_PASS
