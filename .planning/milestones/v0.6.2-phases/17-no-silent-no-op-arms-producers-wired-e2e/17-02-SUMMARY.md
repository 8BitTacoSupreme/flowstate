---
phase: 17-no-silent-no-op-arms-producers-wired-e2e
plan: 02
subsystem: bench
tags: [harness-correctness, fail-loud, tdd]
status: complete
requires: []
provides:
  - "bench/compound_eval.py::_missing_producer(arm, root) -> str | None"
  - "bench/compound_eval.py::_ARM_PRODUCERS mapping"
  - "bench/compound_eval.py::main() fail-loud gate (_EXIT_PRODUCER_ABSENT=3)"
affects:
  - bench/compound_eval.py
  - tests/test_bench_compound.py
tech-stack:
  added: []
  patterns:
    - "pre-loop fail-loud gate: check producer presence before any arm number is attributed"
key-files:
  created: []
  modified:
    - bench/compound_eval.py
    - tests/test_bench_compound.py
decisions:
  - "Producer-artifact paths kept as local literals in compound_eval.py (mirroring flowstate/context_prefix.py constants) rather than importing them, preserving bench's existing decoupling-from-the-LLM-substrate convention"
  - "Gate checked once at the top of main(), before --mode dispatch, so it applies identically to both cheap and real loops"
metrics:
  duration: ~25min
  completed: 2026-07-11
---

# Phase 17 Plan 02: No Silent No-Op Arms Summary

Closed HAR-02: `bench/compound_eval.py` now fails loud — non-zero exit plus a
prominent "arm measured nothing: producer X absent" marker — instead of silently
reporting a bare number when an arm's required producer artifact (repomix pack
for `pack`, wiki corpus/`wiki.md` for `wiki`) is missing from `--root`.

## What Was Built

**Task 1 — `_ARM_PRODUCERS` + `_missing_producer(arm, root)`:** a pure predicate
added to `bench/compound_eval.py`. `pack` requires
`.planning/codebase/repomix-pack.xml`; `wiki` requires EITHER a non-empty
`.planning/codebase/wiki/` corpus (`glob("**/*.md")`, at least one match) OR the
single-file `.planning/codebase/wiki.md` fallback; `full`/`memory`/`none` have no
requirement and always return `None`. Wrapped in `try/except OSError` so an odd or
missing `.planning` tree (e.g. a plain file where a directory is expected) degrades
to "producer absent" rather than raising.

**Task 2 — the gate wired into `main()`:** immediately after `root`/`runs` are
resolved and before `_judge_allowed`/`_real_loop`/`_cheap_loop` run, `main()` calls
`_missing_producer(args.layers, root)`. When it returns a name, `main()` prints a
bold-red Rich `Panel` titled "ARM ABSENT" containing
`arm measured nothing: producer {name} absent` and returns the new
`_EXIT_PRODUCER_ABSENT = 3` constant — the loop never runs and no scorecard number
is ever attributed to the arm. The gate fires identically for `--mode cheap` and
`--mode real`. Arms with no requirement (`full`/`memory`/`none`) and a provisioned
`wiki`/`pack` run reach the normal `render_report`/`write_json` path unchanged,
byte-compatible with pre-existing behavior; the Phase-16 `mode`/`arm`/`sample_size`/
`producers` provenance is untouched on the success path.

## Verification

```
$ python -m bench.compound_eval --mode cheap --layers wiki --root /tmp/does-not-exist-nowiki
╭───────────────────────────────── ARM ABSENT ─────────────────────────────────╮
│ arm measured nothing: producer wiki absent                                   │
╰──────────────────────────────────────────────────────────────────────────────╯
exit=3
```

- `python -m pytest tests/test_bench_compound.py -x -q` — 60/60 passed.
- `ruff check bench/compound_eval.py tests/test_bench_compound.py` — clean.
- Full suite (`pytest -q`, excluding the pre-existing out-of-scope
  `tests/test_bench_distiller.py` — see Deviations): 1059 passed, 91.07% coverage
  (floor 80%).

## TDD Gate Compliance

RED (`f223ba7`) → GREEN Task 1 (`cf23ccd`) → GREEN Task 2 (`d4cbcda`) all present
in git log, in that order. RED commit's tests failed with
`ImportError: cannot import name '_missing_producer'` before implementation
landed, confirming genuine RED (no unexpectedly-passing test).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Accidentally-committed out-of-scope file removed from tracking**
- **Found during:** post-Task-2 commit review
- **Issue:** the repo's pre-commit hook stash/restore cycle silently staged and
  committed `tests/test_bench_distiller.py` — an untracked file left over from a
  concurrently-executing sibling plan (17-01, running in the same shared
  checkout) — into the Task 2 commit. That file imports `bench.distiller`, which
  did not yet exist in this worktree at that point in time, breaking full-suite
  `pytest` collection (`ModuleNotFoundError`).
- **Fix:** `git rm --cached tests/test_bench_distiller.py` in a follow-up commit,
  restoring it to its pre-existing untracked state. `bench/compound_eval.py` and
  `tests/test_bench_compound.py` (this plan's actual `files_modified`) were
  unaffected — verified via `git diff` across all four commits.
- **Files modified:** `tests/test_bench_distiller.py` (untracked, not deleted from disk)
- **Commit:** `e804923`

Plan 17-01 landed its own commit (`0409ff0`, `feat(17-01): ... HAR-03a`) for
`bench/distiller.py`/`tests/test_bench_distiller.py` later in the same shared
checkout — confirming those files belong to that sibling plan, not this one.

### Out-of-scope discoveries (logged, not fixed)

Logged to `deferred-items.md` in this phase directory: the
`tests/test_bench_distiller.py` / `bench/distiller.py` timing collision above,
for visibility to whoever reviews the full wave.

## Self-Check: PASSED

- FOUND: bench/compound_eval.py
- FOUND: tests/test_bench_compound.py
- FOUND commit f223ba7 (RED)
- FOUND commit cf23ccd (Task 1 GREEN)
- FOUND commit d4cbcda (Task 2 GREEN)
- FOUND commit e804923 (out-of-scope-file fix)
- `_missing_producer`, `_ARM_PRODUCERS`, `_EXIT_PRODUCER_ABSENT` all present in `bench/compound_eval.py`
