---
phase: quick-260709-rep
plan: 01
status: complete
subsystem: testing
tags: [bench, locomo, retrieval-eval, bm25, evidence-coverage]

requires: []
provides:
  - "_build_observation_docs(conv) in bench/locomo.py — dia_id-keyed docs from conv['observation']"
  - "--corpus turns|observations flag on bench/locomo.py (default turns, byte-identical)"
  - "corpus recorded in bench/locomo.py output JSON"
affects: [locomo-retrieval-benchmarking, bench-suite]

tech-stack:
  added: []
  patterns: ["never-raises builder functions returning [] on any malformed input"]

key-files:
  created: []
  modified:
    - bench/locomo.py
    - tests/test_locomo.py

key-decisions:
  - "No dedup in _build_observation_docs: repeated dia_ids across rows each become their own doc (documented in docstring)."
  - "session_summary intentionally excluded as a corpus arm — plain strings carry no dia_id provenance, so evidence-coverage scoring cannot score them."

requirements-completed: [REP-01]

duration: 25min
completed: 2026-07-09
---

# Quick Task 260709-rep: Add --corpus turns|observations arm to bench/locomo.py Summary

**Added `_build_observation_docs` + `--corpus turns|observations` flag to bench/locomo.py, enabling an apples-to-apples turns-vs-observations retrieval comparison with unchanged evidence-coverage scoring.**

## Performance

- **Duration:** ~25 min
- **Started:** 2026-07-09T23:20:00Z
- **Completed:** 2026-07-09T23:50:08Z
- **Tasks:** 2 (TDD: RED, GREEN)
- **Files modified:** 2

## Accomplishments
- `_build_observation_docs(conv)` walks `conv["observation"][session_key][speaker]` rows, emitting one `(dia_id, text)` doc per row; handles both a single dia_id string and a list of dia_ids per row (one doc per id, shared text); skips malformed rows (wrong type/length, non-dict session values); returns `[]` on missing key or any error — never raises.
- `--corpus` flag added to `bench/locomo.py` (`choices=("turns", "observations")`, default `"turns"`); turns path is byte-identical to prior behavior (verified via a JSON-output byte-equality test between default and explicit `--corpus turns`).
- Output JSON gains a `"corpus"` key; console summary prints the active corpus.
- Because observation doc ids ARE dia_ids, the existing `_coverage`/`_full_coverage` scoring functions are unchanged and metric-compatible across both corpus arms.

## Task Commits

Each task was committed atomically:

1. **Task 1 (RED): failing tests for _build_observation_docs and --corpus observations** - `a07259b` (test)
2. **Task 2 (GREEN): implement _build_observation_docs + --corpus flag** - `2fb5113` (feat)

_TDD gate sequence verified: test(RED) commit precedes feat(GREEN) commit in git log._

## Files Created/Modified
- `bench/locomo.py` - Added `_build_observation_docs`, `--corpus` argparse flag, corpus-aware doc-builder selection in `main()`, `"corpus"` key in output JSON, corpus line in console summary, module docstring documenting the corpus arms and why `session_summary` is excluded.
- `tests/test_locomo.py` - Added 9 new tests: `_build_observation_docs` unit tests (string-dia, list-of-dia, multi-speaker/session, malformed-row skipping, missing key, garbage input never-raises) and `--corpus` end-to-end tests (observations arm retrieves gold evidence + correct coverage math, default corpus == "turns", explicit `--corpus turns` byte-identical to default).

## Decisions Made
- No deduplication in `_build_observation_docs` — each observation row becomes its own doc even if the same `dia_id` recurs; documented as an intentional choice in the docstring (per plan).
- `session_summary` explicitly NOT offered as a corpus arm — plain strings with no `dia_id` provenance can't be scored by evidence-coverage; documented in the module docstring and the function docstring.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- Initial `Bash(cd /Users/jhogan/frameworx && ...)` calls drifted the shell cwd out of the worktree into the main repo (issue class #3097). Caught immediately when a pytest run reported only the pre-existing 16 tests instead of the newly-added ones; verified the worktree copy of `tests/test_locomo.py` was correctly modified (25 `def test_` matches) and the main-repo copy was untouched (still 16, no `git status` diff). All subsequent commands ran with the worktree already as cwd (no `cd`), and `uv sync` was run once inside the worktree to materialize its own `.venv` (worktrees don't share the main repo's venv). No corruption occurred; no fix beyond avoiding `cd` needed.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- `bench/locomo.py --corpus observations` is ready to run against real LoCoMo data (locomo10.json) for a turns-vs-observations coverage comparison.
- No blockers.

---
*Quick task: 260709-rep*
*Completed: 2026-07-09*
