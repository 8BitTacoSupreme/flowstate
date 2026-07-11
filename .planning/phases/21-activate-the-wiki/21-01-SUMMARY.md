---
phase: 21-activate-the-wiki
plan: 01
subsystem: distiller
status: complete
tags: [wiki, distiller, cli, manifest, staleness, packaging]
requires:
  - flowstate.memory.MemoryStore
  - flowstate.bridge._find_claude
  - flowstate.pack.is_pack_stale (pattern)
provides:
  - flowstate.distiller (production module: main, is_wiki_stale, _WIKI_CORPUS_REL)
  - flowstate distill CLI command
  - InstallEntry kind="wiki"
affects:
  - bench.distiller (now a re-export shim)
tech-stack:
  added: []
  patterns:
    - "production-module promotion with a bench re-export shim (no logic duplication)"
    - "manifest-tracked staleness gate keyed on memory.db mtime (mirrors pack)"
key-files:
  created:
    - flowstate/distiller.py
    - tests/test_distiller.py
  modified:
    - bench/distiller.py
    - flowstate/state.py
    - flowstate/context.py
    - flowstate/cli.py
    - tests/test_bench_distiller.py
    - tests/test_cli.py
decisions:
  - "D-01: distiller logic lives once in flowstate/distiller.py; bench/distiller.py re-exports it"
  - "D-02: explicit `flowstate distill` command with --force/--llm/--model (no --densify — not a real flag)"
  - "D-03: run_pipeline untouched (git diff --exit-code orchestrator.py clean)"
  - "D-04: kind=wiki manifest entry + is_wiki_stale keyed on memory.db mtime"
  - "_locate_claude delegates to bridge._find_claude, mapping '' -> None to preserve the densify contract"
metrics:
  duration: ~11 min
  completed: 2026-07-11
  tasks: 3
  files: 8
---

# Phase 21 Plan 01: Activate the Wiki — Distiller Promotion Summary

Promoted the memory→wiki distiller from bench tooling to a production `flowstate/distiller.py` (importing nothing from `bench/`), exposed it as the explicit `flowstate distill` command, and added a manifest-tracked, `memory.db`-mtime staleness gate mirroring `flowstate pack` — the WIKI-03 producer half.

## What Was Built

**Task 1 — Production module + re-export shim (78dd0b7)**
- Moved the entire distiller body into `flowstate/distiller.py`. The load-bearing packaging fix: the old `from bench.judge import _locate_claude` cannot survive because the wheel ships only `packages=["flowstate"]`. Replaced it with a module-level `_locate_claude()` that delegates to `flowstate.bridge._find_claude` and maps its `""`-on-absent return to `None`, preserving the distiller's `if claude is None:` densify contract. The distiller body calls the module-level name so the `--llm` path resolves the patchable symbol in `flowstate.distiller.__dict__`.
- Rewrote `bench/distiller.py` as a thin re-export shim (`from flowstate.distiller import *` + explicit re-exports of the underscore names tests import).
- Retargeted the three `_locate_claude` monkeypatches in `tests/test_bench_distiller.py` from `bench.distiller` to `flowstate.distiller` (the definition site `main()` now resolves), else they would be inert and the two densify tests would fail.
- Added `tests/test_distiller.py` covering the production import path.

**Task 2 — kind="wiki" manifest + is_wiki_stale (c55ccb8)**
- Extended `InstallEntry.kind` Literal with `"wiki"`.
- Extended `_register`'s checksum-skip branch to `kind not in {"memory", "wiki"}` — the wiki corpus is a DIRECTORY, so `_sha256_of` must not run on it.
- Added `is_wiki_stale(root, state)` mirroring `is_pack_stale` but keyed on `memory.db` mtime vs the manifest entry's `created_at`. Absent entry → stale; memory.db newer → stale; memory.db absent/older → not stale.

**Task 3 — `flowstate distill` command (7084510)**
- Added `@main.command("distill")` mirroring `pack`: `--root/--force/--llm/--model`. Skips with a dim "up to date" message when a wiki entry exists and `not is_wiki_stale` (unless `--force`); otherwise calls `distiller.main` (passing `--force` through so the distiller's own populated-corpus skip does not block a staleness-driven regen), registers the corpus dir on rc==0, and `sys.exit(rc)` on failure.

## Deviations from Plan

None — plan executed exactly as written. The plan's context already corrected D-02's phantom `--densify` flag to the real `--force/--llm/--model` surface; that correction was honored.

## Verification

- `uv run python -m pytest tests/test_distiller.py tests/test_bench_distiller.py tests/test_cli.py tests/test_state.py -q` → 107 passed.
- Full suite: **1183 passed, 91.23% coverage** (≥80% gate met).
- `uv run ruff check` on all touched files → clean.
- `git diff --exit-code flowstate/orchestrator.py` → clean (D-03 fence respected).
- Packaging: `python -c "import sys; sys.modules.pop('bench', None); import flowstate.distiller"` exits 0; `grep -c bench flowstate/distiller.py` → 0.

## Requirements Satisfied

- **WIKI-03** (producer half): `flowstate distill` writes a manifest-tracked, staleness-gated `.planning/codebase/wiki/` corpus from memory.db, distiller logic living once in flowstate/ and bench re-importing it.

## Notes for Downstream (Plan 21-02+)

- The consumer half (opt-in `wiki_layer` config flag + orchestrator `include_layers` union D-06, `[semantic]`-absent warning D-07, dogfood smoke-test D-08) is NOT in this plan. The D-03 fence means nothing auto-invokes the distiller yet — a user/pipeline runs `flowstate distill` after a run, and the next run's wiki layer reads the fresh corpus.

## Self-Check: PASSED

All created files and commits (78dd0b7, c55ccb8, 7084510, b8f0b2e) verified present.
