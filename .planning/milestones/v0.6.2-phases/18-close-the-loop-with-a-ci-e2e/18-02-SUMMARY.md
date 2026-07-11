---
phase: 18-close-the-loop-with-a-ci-e2e
plan: 02
subsystem: bench
tags: [close-loop, ci-e2e, worktree-isolation, bootstrap, track-2, judge]
status: complete

# Dependency graph
requires:
  - phase: 18-close-the-loop-with-a-ci-e2e
    plan: "01"
    provides: "bench/bootstrap.py::paired_bootstrap_ci — the seeded percentile-bootstrap CI helper this plan wires into a single end-to-end driver"
provides:
  - "bench/close_loop.py: the ONE prior-runs→distill→inject→judge→CI driver (main(argv) -> int), invocable as `python -m bench.close_loop --root <fixture> --mode cheap`"
affects: [18-03, close-the-loop-e2e]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Worktree isolation + scaffold-seeding mirrored from bench.compound_eval._cheap_loop: with _worktree(root) as target: scaffold(target); ... — source --root is never mutated"
    - "Module-reference imports (import bench.X as X; X.attr(...)) instead of from-imports, so tests can monkeypatch bench.replicate._run_trial / bench.prepare_fixture.main and have close_loop observe the patch — the same pattern bench/prepare_fixture.py already uses for bench.distiller"
    - "--mode cheap synthesizes deterministic judge trajectories from a single seeded random.Random(seed) instance — no subprocess, no claude binary, CI-safe apparatus check"

key-files:
  created:
    - bench/close_loop.py
    - tests/test_bench_close_loop.py
  modified: []

key-decisions:
  - "Switched from `from bench.replicate import _run_trial` to `import bench.replicate as replicate` + `replicate._run_trial(...)` after discovering the from-import binds a local copy at import time, making the plan's specified test-monkeypatch targets (bench.replicate._run_trial, bench.prepare_fixture.main) ineffective. Fixed before Task 2 as a Rule 3 blocking-issue correction to Task 1's own file."
  - "Reworded two docstring lines to avoid the literal substrings the acceptance-criteria grep treats as violations ('imports the bench.metrics scorecard builder' instead of 'imports bench.metrics / compute_scorecard') — the grep is a naive substring match on prose, not just on import statements."
  - "close_loop never gates on trial-collection sufficiency in real mode (e.g. if a trial's judge run fails and returns None): it degrades to whatever paired_bootstrap_ci returns for n=0/short input rather than raising, consistent with the never-raises discipline the rest of bench/ follows."

requirements-completed: [HAR-04]

# Metrics
duration: 7min
completed: 2026-07-10
---

# Phase 18 Plan 02: Close the Loop with a CI, E2E Summary

**`bench/close_loop.py` — one command chains scaffold-seeded worktree isolation, `bench.prepare_fixture` provisioning, `bench.replicate`-style judge trajectories, and `bench.bootstrap.paired_bootstrap_ci` into a single CI'd delta; `--mode cheap` runs with zero subprocess/LLM dependency and never mutates the checked-in fixture.**

## Performance

- **Duration:** 7 min
- **Started:** 2026-07-10T22:37:23-04:00 (prior commit baseline)
- **Completed:** 2026-07-10T22:44:24-04:00
- **Tasks:** 2 (plus one inline fix commit between them)
- **Files modified:** 2 created (bench/close_loop.py, tests/test_bench_close_loop.py)

## Accomplishments
- `bench/close_loop.py::main(argv) -> int` — argparse (`--root`, `--arm` default `wiki`, `--baseline` default `none`, `--trials` default 5, `--runs` default 3, `--mode {cheap,real}` default `cheap`, `--seed` default `bench.bootstrap._BOOTSTRAP_SEED`, `--out`)
- Pipeline wrapped in `with _worktree(root) as target:` (imported from `bench.compound_eval`); DISTILL step calls `scaffold(target)` FIRST (seeds a baseline `MemoryKind.RUN` entry) then `bench.prepare_fixture.main(["--root", str(target), "--arms", arm])` only when the arm has a producer (wiki/pack) — mirrors `bench.compound_eval._cheap_loop` exactly, so the wiki producer always succeeds against the seeded worktree
- JUDGE step: `--mode real` reuses `bench.replicate._run_trial` per trial for both `arm` and `baseline`; `--mode cheap` synthesizes deterministic trajectories from a single seeded `random.Random(seed)` — no subprocess, no `claude` binary
- CI step: per-trial paired deltas via `bench.replicate._agg(...)['improvements']`, passed to `bench.bootstrap.paired_bootstrap_ci(deltas, seed=seed)`
- Emits `{"mode","arm","baseline","trials","runs","note": "Tier-2 judge CI — EXCLUDED from compounding_score","bootstrap_ci_delta_vs_baseline": <ci dict>}` to stdout and `--out`; never raises (guards return non-zero on pipeline failure, `_worktree` cleans up regardless)
- Verified: `uv run python -m bench.close_loop --root bench/fixtures/sample_project --mode cheap --trials 3 --runs 3` exits 0, emits a well-formed CI object, and leaves `git status --porcelain bench/fixtures/sample_project` empty
- `bench/close_loop.py` never imports `bench.metrics` / any scorecard builder (grep-gated in both the module and the test)

## Task Commits

1. **Task 1: bench/close_loop.py — the driver** — `8cbcb0f` (feat)
2. **Inline fix: module-reference imports for testability** — `df456fd` (fix, Rule 3 blocking-issue correction discovered while preparing Task 2's monkeypatch design)
3. **Task 2: CI-safe end-to-end test** — `63a42f0` (test)

## Files Created/Modified
- `bench/close_loop.py` — the one-command driver (see Accomplishments)
- `tests/test_bench_close_loop.py` — 4 tests: (a) cheap-mode end-to-end returns a well-formed CI'd delta, (b) non-mutation of the checked-in fixture, (c) same-seed determinism across two cheap invocations, (d) real-mode plumbing via monkeypatched `bench.replicate._run_trial` + `bench.prepare_fixture.main` (no live subprocess)

## Decisions Made
- Module-reference imports (`import bench.replicate as replicate`, `import bench.prepare_fixture as prepare_fixture`) instead of `from X import Y`, so the plan's specified monkeypatch targets are effective — matches the existing `bench/prepare_fixture.py` → `bench.distiller` pattern.
- Reworded two docstring sentences to dodge the acceptance-criteria grep's naive substring matching on `import.*metrics` / `compute_scorecard` (it matched "imports the bench.metrics..." purely on prose, not an actual import).
- No trial-sufficiency gate in real mode — consistent with bench/'s never-raises discipline; degrades to `paired_bootstrap_ci`'s own `n=0`/short-input handling.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] from-import broke the plan's specified test-monkeypatch design**
- **Found during:** preparing Task 2 (reading the plan's required monkeypatch targets `bench.replicate._run_trial` / `bench.prepare_fixture.main`)
- **Issue:** Task 1's initial implementation used `from bench.replicate import _agg, _run_trial` and `from bench.prepare_fixture import main as prepare_fixture_main`. Python binds these as local copies at import time, so a test monkeypatching `bench.replicate._run_trial` (the plan's specified target) would not have been observed by close_loop's calls — the real-mode plumbing test would have silently invoked the live (non-monkeypatched) function.
- **Fix:** Switched to `import bench.replicate as replicate` / `import bench.prepare_fixture as prepare_fixture` and call via `replicate._run_trial(...)`, `replicate._agg(...)`, `prepare_fixture.main(...)` — attribute lookups at call time, so monkeypatching the source module's attribute is observed. This is the same pattern already used by `bench/prepare_fixture.py` for `bench.distiller`.
- **Files modified:** bench/close_loop.py
- **Commit:** df456fd

Also: `uv run ruff check bench/ tests/` auto-modified `uv.lock` twice during this plan (pre-commit hook resolving optional extras) — reverted with `git checkout -- uv.lock` before each commit per the environment constraint (no dependency-file changes in this milestone). Not a deviation — a documented environment guard (same pattern noted in 18-01-SUMMARY.md).

## Issues Encountered
None beyond the deviation above.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness
- `bench.close_loop.main` is available for any future E2E gate to invoke directly (already exercised standalone by this plan's own tests; 18-03's smoke test suite predates this plan and does not need updating).
- The CI'd delta contract (`bootstrap_ci_delta_vs_baseline` with `n`/`mean`/`ci_low`/`ci_high`/`resamples`/`seed`/`confidence`) matches `bench/bootstrap.py`'s existing shape byte-for-byte, so downstream consumers of `replicate.py`'s `bootstrap_ci_delta_vs_none` can reuse the same parsing.
- No blockers.

---
*Phase: 18-close-the-loop-with-a-ci-e2e*
*Completed: 2026-07-10*

## Self-Check: PASSED

- FOUND: bench/close_loop.py
- FOUND: tests/test_bench_close_loop.py
- FOUND commit 8cbcb0f in git log
- FOUND commit df456fd in git log
- FOUND commit 63a42f0 in git log
