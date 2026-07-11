---
phase: 17-no-silent-no-op-arms-producers-wired-e2e
plan: 01
subsystem: bench
tags: [memory-to-wiki, distiller, wiki-corpus, harness, HAR-03]

# Dependency graph
requires:
  - phase: 11-semantic-wiki-retrieval
    provides: "_semantic_wiki_layer reader glob contract (_WIKI_CORPUS_DIR = .planning/codebase/wiki)"
  - phase: 6
    provides: "MemoryStore.get_by_kind / MemoryKind / MemoryEntry persistence layer"
provides:
  - "bench/distiller.py — deterministic memory->wiki article-corpus producer, article per non-empty MemoryKind"
  - "--llm optional one-pass densification per article via bench.judge._locate_claude, never-raises fallback"
  - "closes HAR-03b generator/reader mismatch: wikigen.py's single wiki.md never fed the corpus-globbing reader; distiller.py does"
affects: [17-03, wiki-bench-arm, compound_eval]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "bench producer modeled structurally on bench/wikigen.py (argparse --root/--force/--model, never-raises, __main__ guard)"
    - "in-memory article build before any disk write — a mid-loop densification failure never leaves a partial corpus"

key-files:
  created:
    - bench/distiller.py
    - tests/test_bench_distiller.py
  modified: []

key-decisions:
  - "TOOL_RUN kind excluded from the article set — ephemeral run-log noise, not durable knowledge (DECISION/INSIGHT/RESEARCH/STRATEGY/RUN only)"
  - "Articles built fully in-memory before any write to disk, so a mid-loop --llm failure can never leave a half-written corpus"

patterns-established:
  - "Producer/reader contract check: any new bench producer targeting _WIKI_CORPUS_DIR must satisfy sorted(corpus_dir.glob('**/*.md')) with real per-kind .md files, not a single aggregate file"

requirements-completed: [HAR-03]

# Metrics
duration: 9min
completed: 2026-07-11
---

# Phase 17 Plan 01: Memory-to-Wiki Distiller Summary

**`bench/distiller.py` reads `memory.db` and writes a real `.planning/codebase/wiki/` article corpus (one `.md` per non-empty MemoryKind), closing the producer/reader mismatch where `wikigen.py`'s single `wiki.md` never fed the corpus-globbing Phase-11 semantic reader.**

## Performance

- **Duration:** ~9 min
- **Started:** 2026-07-10T21:12:00-04:00 (approx, first file read)
- **Completed:** 2026-07-11T01:23:09Z
- **Tasks:** 2
- **Files modified:** 2 (both created)

## Accomplishments
- `bench/distiller.py::main()` reads `memory.db` via `MemoryStore.get_by_kind` across DECISION/INSIGHT/RESEARCH/STRATEGY/RUN, groups into one article per non-empty kind, and writes deterministic numeric+kind-named `.md` files (`01-decisions.md`, `02-insights.md`, ...) under `.planning/codebase/wiki/` — the exact directory `flowstate/context_prefix.py::_semantic_wiki_layer` globs.
- Fail-loud empty-memory guard: zero entries across all kinds → non-zero exit, stderr message, **no files written** (no partial/empty corpus).
- Force/skip guard: an existing populated corpus is left untouched unless `--force`.
- `--llm` optionally densifies each article via one bounded `claude --print --max-turns 1` call (reusing `bench.judge._locate_claude`); any failure (locator absent, non-zero return, empty stdout, raise, timeout) degrades to the deterministic article text — the module never raises and the default (no `--llm`) path spawns zero subprocesses.
- Live end-to-end smoke-tested (not just mocked): seeded a real `memory.db`, ran `python -m bench.distiller --root <tmp>`, confirmed 2 real `.md` files written; separately confirmed an empty `memory.db` returns exit code 1 with zero files written.

## Task Commits

Each task was committed atomically, following full RED→GREEN TDD per task:

1. **Task 1: Deterministic memory→wiki distiller core + guards**
   - RED commit content ("test(17-01): red — distiller article-corpus tests fail (module missing)") was captured into a concurrent worktree commit (`d4cbcda`) due to a shared-worktree race, then untracked again by that plan's self-correction (`e804923`); no standalone RED hash exists for Task 1 — see Issues Encountered
   - `0409ff0` feat(17-01): deterministic memory-to-wiki distiller core (HAR-03a) — includes the test file, re-added and committed cleanly (RED+GREEN content both present at this hash)
2. **Task 2: Optional one-pass --llm article densification (never-raises)**
   - `91c23ef` test(17-01): red — --llm densification tests fail (not wired yet)
   - `be011be` feat(17-01): wire --llm one-pass article densification (HAR-03a)

_Note: TDD tasks had exactly the RED→GREEN sequence per task (no refactor commit needed)._

## Files Created/Modified
- `bench/distiller.py` - memory→wiki article-corpus distiller (deterministic core + `--llm` densification)
- `tests/test_bench_distiller.py` - 9 behavior tests: corpus shape, empty-memory guard, force/skip guard, `--llm` locator-absent/raising-subprocess/success paths, default-path subprocess-free assertion

## Decisions Made
- Excluded `MemoryKind.TOOL_RUN` from the distilled article set (ephemeral run-log noise, not durable wiki knowledge) — matches the plan's explicit kind list (DECISION, INSIGHT, RESEARCH, STRATEGY, RUN).
- Built each article fully in-memory before any disk write, so a `--force` regeneration that fails mid-loop (e.g. a hung `--llm` call on article 2 of 3) never leaves a half-written corpus — stronger than the plan's literal guard language, applying the same "never a partial corpus" principle from the empty-memory guard to the force-regeneration path.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed ruff SIM105 lint violation in the store-close finally block**
- **Found during:** Task 1 commit (pre-commit ruff hook)
- **Issue:** `try: store.close() except Exception: pass` triggered `SIM105 Use contextlib.suppress(Exception)`
- **Fix:** Replaced with `with contextlib.suppress(Exception): store.close()`
- **Files modified:** bench/distiller.py
- **Commit:** 0409ff0

---

**Total deviations:** 1 auto-fixed (1 lint/style)
**Impact on plan:** Cosmetic only; no behavior change. No scope creep.

## Issues Encountered

**Shared-worktree concurrency hazard (infrastructure, not a plan deviation):** This worktree was concurrently occupied by another executor agent running plan 17-02 (`bench/compound_eval.py`'s `_missing_producer` gate, HAR-02). Because both agents share one git index/working tree, several `git add`/`git commit` operations raced:
- My first RED commit for `tests/test_bench_distiller.py` got swept into 17-02's own commit `d4cbcda` (their staged snapshot picked up my staged file at commit time). 17-02's agent self-corrected this in `e804923` ("fix(17-02): untrack accidentally-committed tests/test_bench_distiller.py"), after which the file was untracked and I re-committed it cleanly as part of `0409ff0`.
- A `git status` mid-sequence briefly showed a staged deletion of `tests/test_bench_distiller.py` (D) alongside an untracked copy (??) — resolved with `git reset -- tests/test_bench_distiller.py` (index-only unstage, no working-tree mutation, no `git clean`/`checkout .`/`reset --hard`) before re-adding and re-committing.
- No content was lost; both plans' final `git log` state is clean and each commit contains exactly its own plan's files. Verified via `git show <hash> --stat` at each step.
- `.planning/STATE.md` and `uv.lock` carry unrelated unstaged modifications from the concurrent 17-02 session (and possibly the orchestrator) for the entire duration of this plan's execution — left untouched per this plan's explicit instruction not to write STATE.md/ROADMAP.md, and because they are out of this plan's `files_modified` scope.

## TDD Gate Compliance

- **Task 2** ("Optional one-pass --llm article densification"): clean RED→GREEN pair in git log — `91c23ef` (test, red, 3 failing tests verified via `AttributeError: ... has no attribute '_locate_claude'`) → `be011be` (feat, green, all 9 tests pass, `ruff check` clean).
- **Task 1** ("Deterministic memory→wiki distiller core + guards"): the RED phase was genuinely executed and verified (`ModuleNotFoundError: No module named 'bench.distiller'` confirmed before any implementation existed), but no standalone `test(...)` commit survives in git log for it — a shared-worktree race (see Issues Encountered) absorbed the first RED commit into a concurrent plan's commit (`d4cbcda`), which was then self-corrected by that plan (`e804923`, untracking the file again). The test file was re-added together with the passing implementation in a single commit (`0409ff0`), so git history shows RED-content and GREEN-content landing together rather than as two separate commits. The actual TDD discipline (write failing test → verify fail → implement → verify pass) was followed in real time; only the commit-graph artifact of the race is non-standard. No code or test correctness impact.

## User Setup Required

None - no external service configuration required. `--llm` is opt-in and degrades gracefully when `claude` is not on PATH.

## Next Phase Readiness

- The `wiki` bench arm now has a real corpus producer whose output shape the Phase-11 semantic reader actually consumes — `_missing_producer` (landed in 17-02, same phase) can now find a satisfied `wiki` requirement once `python -m bench.distiller --root <proj>` has been run.
- `bench/wikigen.py` (single-file `wiki.md`) remains in place unmodified; it still satisfies the reader's static-fallback path (`_read_wiki_layer`) but not the semantic corpus glob. Whichever plan wires the compounding-eval harness to actually invoke a wiki producer before scoring the `wiki` arm should call `bench.distiller`, not `bench.wikigen`, to reach the corpus-glob code path.
- Full test suite green: 1068 passed, 91.07% coverage (run after both 17-01 and 17-02 landed in this shared worktree).

---
*Phase: 17-no-silent-no-op-arms-producers-wired-e2e*
*Completed: 2026-07-11*

## Self-Check: PASSED

- FOUND: bench/distiller.py
- FOUND: tests/test_bench_distiller.py
- FOUND: .planning/phases/17-no-silent-no-op-arms-producers-wired-e2e/17-01-SUMMARY.md
- FOUND commit: 0409ff0 (feat, Task 1 core)
- FOUND commit: 91c23ef (test, Task 2 red)
- FOUND commit: be011be (feat, Task 2 densification)
- FOUND commit: f531583 (docs, plan complete)
