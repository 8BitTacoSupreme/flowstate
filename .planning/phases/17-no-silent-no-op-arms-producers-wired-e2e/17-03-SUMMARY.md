---
phase: 17-no-silent-no-op-arms-producers-wired-e2e
plan: 03
subsystem: bench
tags: [prepare-fixture, wiki, pack, harness, HAR-03]
status: complete

requires:
  - phase: 17-01
    provides: "bench/distiller.py::main — wiki article-corpus producer"
  - phase: 17-02
    provides: "bench/compound_eval.py::_missing_producer / _ARM_PRODUCERS — the fail-loud gate this fixture feeds"
provides:
  - "bench/prepare_fixture.py::main(argv) -> int — single entry point provisioning the pack and wiki producers"
affects: [bench.compound_eval, wiki-bench-arm, pack-bench-arm]

tech-stack:
  added: []
  patterns:
    - "producer wiring, not reimplementation: prepare_fixture calls flowstate.pack.run_pack and bench.distiller.main directly, no duplicated logic"
    - "per-producer status line + non-zero-on-any-failure, matching the fail-loud discipline established in 17-02"

key-files:
  created:
    - bench/prepare_fixture.py
    - tests/test_bench_prepare_fixture.py
  modified: []

key-decisions:
  - "arms without a producer (full/memory/none) are accepted as a documented no-op rather than rejected by argparse choices, matching the plan's explicit acceptance criterion"
  - "--llm/--model always exist on prepare_fixture's own CLI but default LLM off; forwarded to the distiller only when --llm is passed, keeping the default path subprocess-free (inherits distiller's Task 2 guarantee)"

requirements-completed: [HAR-03]

metrics:
  duration: ~12min
  completed: 2026-07-11
---

# Phase 17 Plan 03: prepare_fixture Entry Point Summary

**`bench/prepare_fixture.py` is the ONE `prepare-fixture` command (HAR-03, success criterion 3) that provisions every arm's producer artifact — repomix pack and wiki article corpus — before the `bench.compound_eval` arm matrix runs, wiring `flowstate.pack.run_pack` and `bench.distiller.main` without reimplementing either.**

## What Was Built

**Task 1 — `bench/prepare_fixture.py::main`:** a single `python -m bench.prepare_fixture --root <proj>` entry point.

- `--arms` (comma-separated or repeatable) selects which producers run; default is `pack,wiki` (both).
- `pack` arm calls `flowstate.pack.run_pack(root)` and treats `PackResult.success` as the outcome, surfacing `.error` on failure.
- `wiki` arm calls `bench.distiller.main(["--root", str(root), ...])`, forwarding `--force` always and `--llm`/`--model` only when `--llm` is passed (LLM stays off by default, matching the distiller's own subprocess-free default path).
- Arms with no producer (`full`/`memory`/`none`) are accepted and reported as a no-op skip, not a failure.
- Each producer's outcome is printed as one Rich-console line (`built` / `failed — <reason>`); a producer exception is caught and reported as that producer's failure — `main()` never raises.
- Overall return is `0` iff every requested producer succeeded, else `1`, with a summary line naming the failed producers.

**Task 2 — lint + full-suite coverage gate:** ran `ruff check`/`ruff format --check` across `flowstate/`, `bench/`, `tests/` (clean) and the full suite with coverage. No regressions from this phase's changes — no fixes needed.

## Verification

- `tests/test_bench_prepare_fixture.py` (4 tests, all pass):
  - `--arms wiki` on a root with a populated `memory.db` builds the corpus (`>=2` `*.md` files) and returns 0.
  - `--arms wiki` on a root with an empty `memory.db` returns non-zero, output reports `wiki` as `failed`.
  - `--arms pack` with `run_pack` monkeypatched to `PackResult(success=False, ...)` returns non-zero, output reports `pack` as `failed`.
  - Default `--arms` (no flag) invokes both `run_pack` and `bench.distiller.main`; an all-success stub run returns 0.
- `python -m pytest tests/test_bench_prepare_fixture.py -x -q` — 4/4 passed.
- Full suite: `python -m pytest tests/ --cov=flowstate --cov-fail-under=80 -q` — **1072 passed**, coverage **91.07%** (floor 80%).
- `ruff check flowstate/ bench/ tests/` — clean. `ruff format --check bench/ tests/` — 66 files already formatted.

## Task Commits

Full RED → GREEN TDD for Task 1:

1. **Task 1: prepare_fixture entry point wiring per-arm producers**
   - `160ab0a` test(17-03): red — prepare_fixture tests fail (module missing) — confirmed genuine RED: `ModuleNotFoundError: No module named 'bench.prepare_fixture'` at collection.
   - `dcadada` feat(17-03): prepare_fixture entry point wiring per-arm producers (HAR-03) — implementation + a ruff import-order auto-fix in the RED-committed test file (pre-commit hook, ruff `I001`), landed in the same commit since it only touches import ordering in a file this task owns.
2. **Task 2: repo lint + full-suite coverage gate** — verification only, no code changes required (suite was already green); no commit.

## Files Created/Modified

- `bench/prepare_fixture.py` — the prepare-fixture entry point (`main`, `_run_pack_producer`, `_run_wiki_producer`, `_parse_arms`, `_build_parser`)
- `tests/test_bench_prepare_fixture.py` — 4 behavior tests covering wiki success/failure, pack producer wiring via monkeypatched `run_pack`, and default-arms both-producers dispatch

## Decisions Made

- Kept `--arms` un-choice-restricted in argparse (plain string, comma/repeat parsing) rather than `choices=(...)` so `full`/`memory`/`none` can be passed through as documented no-ops without special-casing argparse validation — matches the plan's explicit acceptance criterion ("Passing arms with no producer ... is a no-op that does not fail").
- `--llm`/`--model` exist on `prepare_fixture`'s CLI (per the plan's action text) but are only forwarded to the distiller when `--llm` is explicitly passed, so the default `prepare-fixture` invocation never spawns a `claude` subprocess — consistent with the distiller's own Task 2 default-path guarantee (17-01).

## Deviations from Plan

None — plan executed exactly as written. The one auto-fixed lint issue (ruff `I001` import-order in `tests/test_bench_prepare_fixture.py`) is cosmetic only, folded into the GREEN commit since it only touches this task's own test file.

## TDD Gate Compliance

Clean RED → GREEN pair in git log for Task 1: `160ab0a` (test, red, `ModuleNotFoundError` confirmed via `pytest -x -q` before any implementation existed) → `dcadada` (feat, green, all 4 tests pass, `ruff check`/`ruff format --check` clean). No refactor commit needed.

## User Setup Required

None — no external service configuration required. Default path (`--arms pack,wiki`, no `--llm`) requires only `repomix` on PATH (or `FLOWSTATE_REPOMIX_BIN`) for the pack producer and a populated `memory.db` for the wiki producer; both degrade to a reported, non-zero failure (not a crash) when absent.

## Next Phase Readiness

- HAR-03's three success criteria are now all landed within this phase: (a) 17-01 gave the wiki arm a real corpus producer whose output shape the Phase-11 semantic reader consumes; (b) 17-02 made `bench.compound_eval` fail loud when an arm's producer artifact is absent; (c) this plan gives operators the ONE command (`python -m bench.prepare_fixture --root <proj>`) to run before the arm matrix so (b)'s gate is satisfied rather than tripped.
- `bench/wikigen.py` (single-file `wiki.md`) remains unmodified and unused by `prepare_fixture` — `_missing_producer`'s wiki check accepts either the corpus or the legacy single file, but only the corpus-producing `bench.distiller` is wired into `prepare_fixture`, per 17-01's guidance.
- Full test suite green: 1072 passed, 91.07% coverage (run after this plan landed, whole repo).

---
*Phase: 17-no-silent-no-op-arms-producers-wired-e2e*
*Completed: 2026-07-11*
