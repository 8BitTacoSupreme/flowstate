---
phase: 19-the-tax
plan: 02
status: complete
subsystem: bench-consumption
tags: [tokens, latency, run-journal, run-snapshot, consumption-accounting]

# Dependency graph
requires:
  - phase: 19-01
    provides: "ClaudeBridge cumulative totals (total_tokens_in/out/cache_read/total_wall_clock_s) + BridgeResult.usage on output_format=json"
provides:
  - "RunSnapshot.tokens_in/tokens_out/cache_read (int) + wall_clock_s (float|None) — real per-run consumption"
  - "RUN journal entry metadata keys tokens_in/tokens_out/cache_read/wall_clock_s"
  - "capture_run_snapshot populates consumption from the latest RUN entry"
affects: [19-VERD, bench/report.py, cost-per-success]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Pure-carriage dataclass fields appended with defaults — scorer never reads them, compute_scorecard stays byte-identical"
    - "Type-guarded metadata.get reads defaulting to 0/None (never-raise), matching the artifacts_changed discipline"

key-files:
  created: []
  modified:
    - bench/metrics.py
    - bench/capture.py
    - flowstate/journal.py
    - flowstate/orchestrator.py
    - flowstate/tools/research.py
    - flowstate/tools/strategy.py
    - tests/test_bench_compound.py
    - tests/test_journal.py

key-decisions:
  - "New consumption fields appended AFTER layers_present with defaults so every existing positional/keyword RunSnapshot construction site stays valid"
  - "prefix_tokens kept as the Track-1 GROWTH signal (input-context SIZE) — NOT repurposed for consumption; the two quantities are distinct and both carried"
  - "orchestrator passes wall_clock_s=None on dry runs (dry bridge measures no real work); tokens are already 0 from a dry bridge"
  - "Adapter bridge calls switched to output_format=json (Plan 01 guarantees byte-identical .output) so usage is captured with no extra LLM call"

patterns-established:
  - "T-19-03 tampering-boundary guard: capture reads RUN usage keys via metadata.get with type-guards + 0/None fallback"

requirements-completed: [TAX-02]

# Metrics
duration: ~14min
completed: 2026-07-11
---

# Phase 19 Plan 02: The Tax — Real per-run consumption into RunSnapshot Summary

**`RunSnapshot` now carries real `tokens_in`/`tokens_out`/`cache_read`/`wall_clock_s`, sourced from the shared pipeline bridge's cumulative totals (Plan 01) and threaded end-to-end — orchestrator → `append_run_entry` RUN metadata → `capture_run_snapshot` — while `prefix_tokens` keeps its distinct Track-1 growth role and `compute_scorecard` stays provably byte-identical.**

## Performance

- **Duration:** ~14 min
- **Tasks:** 3/3
- **Files modified:** 8 (6 source, 2 test)
- **Tests:** 1127 passed, 91.17% coverage (≥80% gate met)

## Accomplishments

- **Task 1 — RunSnapshot consumption fields:** Appended four frozen fields to `RunSnapshot` after `layers_present` — `tokens_in: int = 0`, `tokens_out: int = 0`, `cache_read: int = 0`, `wall_clock_s: float | None = None` — as pure carriage that no axis reads. `_zeroed_snapshot` sets them to 0/0/0/None. A new test scores a compounding sequence twice (defaults vs. nonzero consumption) and asserts every axis + headline + verdict is identical, proving `compute_scorecard` is unchanged. Established the RUN-entry metadata key contract (`tokens_in`/`tokens_out`/`cache_read`/`wall_clock_s`).
- **Task 2 — producer side:** `append_run_entry` gained four keyword-only params written into the RUN metadata dict alongside `artifacts_changed`. `orchestrator.run_pipeline` reads `bridge.total_tokens_in/out/cache_read/total_wall_clock_s` and passes them at the existing `append_run_entry` call, passing `wall_clock_s=None` for dry runs. The three pipeline adapter bridge calls (research.py ×2, strategy.py ×1) now pass `output_format="json"` so usage is captured; adapters still consume only `br.output`, which Plan 01 guarantees byte-identical.
- **Task 3 — reader side:** In the existing `run_entries[0]` read block of `capture_run_snapshot`, the four consumption keys are pulled via `metadata.get(...)` with `isinstance` type-guards, defaulting to 0/0/0/None on absence or oddity (never raises), and passed into the `RunSnapshot(...)` construction. `prefix_tokens` (`len(prefix)//_CHARS_PER_TOKEN`) is untouched — it remains the Track-1 growth signal, verified decoupled from the injected token count by a dedicated test.

## Verification

- `uv run python -m pytest tests/test_bench_compound.py tests/test_journal.py -x` — green.
- `uv run python -m pytest` (full suite) — 1127 passed, 91.17% coverage.
- `uv run ruff check` over all six source + two test files — clean.
- Sanity: `compute_scorecard` byte-identical under the new fields (Task 1 test); `prefix_tokens` role unchanged (Task 3 test).

## TDD Gate Compliance

All three tasks followed RED → GREEN. Gate commits present in git log:
- Task 1: RED `2625cda` → GREEN `0edfca8`
- Task 2: RED `0078520` → GREEN `c712782`
- Task 3: RED `085fad6` → GREEN `f3534aa`

## Deviations from Plan

None — plan executed exactly as written. (Ruff auto-fixed import ordering in the Task 3 RED test on first commit attempt; re-staged and committed, no behavior change.)

## Threat Surface

- **T-19-03 (Tampering, mitigated):** capture reads the RUN usage keys via `metadata.get(...)` with `isinstance` guards and 0/None fallback, matching the never-raise discipline already used for `artifacts_changed`. No external input crosses the boundary — numeric aggregates only.
- **T-19-04 (Information disclosure, accepted):** token counts are non-sensitive aggregate integers in the local `memory.db`.
- **T-19-SC:** No new packages introduced.

No new threat surface beyond the plan's registered boundary.

## Self-Check: PASSED

- `bench/metrics.py` — FOUND (tokens_in/tokens_out/cache_read/wall_clock_s on RunSnapshot)
- `bench/capture.py` — FOUND (reads four keys; _zeroed_snapshot updated)
- `flowstate/journal.py` — FOUND (four kwargs written to RUN metadata)
- Commits 2625cda, 0edfca8, 0078520, c712782, 085fad6, f3534aa — FOUND in git log
