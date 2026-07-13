---
phase: 21-activate-the-wiki
plan: 02
subsystem: context-prefix
status: complete
tags: [wiki, context-prefix, orchestrator, opt-in, degradation, byte-identity]
requires:
  - flowstate.context_prefix.build_context_prefix
  - flowstate.context_prefix._semantic_wiki_layer
  - flowstate.embeddings.get_embedder
provides:
  - flowstate.state.ProjectPreferences.wiki_layer
  - flowstate.context_prefix._STANDARD_LAYERS
  - flowstate.context_prefix._warn_semantic_absent
affects:
  - flowstate.orchestrator.run_pipeline (build_context_prefix call site only)
tech-stack:
  added: []
  patterns:
    - "opt-in layer union defined once (_STANDARD_LAYERS) to prevent drift"
    - "single-probe embedder capture reused for retrieval and warning gate"
    - "once-per-process console warning via module-level sentinel"
key-files:
  created: []
  modified:
    - flowstate/state.py
    - flowstate/context_prefix.py
    - flowstate/orchestrator.py
    - tests/test_state.py
    - tests/test_orchestrator.py
    - tests/test_context_prefix.py
decisions:
  - "D-05: ProjectPreferences.wiki_layer bool default False; flag off => include_layers=None => byte-identical"
  - "D-06: flag on => _STANDARD_LAYERS | {wiki} (all six keys), NOT {wiki} alone; union defined once as a module constant"
  - "D-07: flag on + embedder absent => one-time warning naming pip install flowstate[semantic], degrade to static reader, never crash"
  - "D-03: only the orchestrator build_context_prefix call site changed; run_pipeline distill side untouched"
metrics:
  duration: ~15 min
  completed: 2026-07-11
  tasks: 2
  files: 6
---

# Phase 21 Plan 02: Activate the Wiki — Opt-in Production Wiring Summary

Activated the dormant Phase-11 semantic wiki layer in production behind an opt-in `wiki_layer` flag: the orchestrator now passes the full standard-layer set unioned with `{"wiki"}` when the flag is on, stays byte-identical (`include_layers=None`) when off, and degrades a missing `[semantic]` extra into a single console warning rather than a crash — the WIKI-04/WIKI-05 consumer half.

## What Was Built

**Task 1 — Opt-in flag + _STANDARD_LAYERS union wiring (58d140f)**
- Added `ProjectPreferences.wiki_layer: bool = False` (D-05).
- Defined `_STANDARD_LAYERS = frozenset({"fixtures","pack","gotchas","memory","since_last_run"})` as a single module constant in `context_prefix.py` and imported it into the orchestrator so the opt-in union cannot drift from the keys `_included()` recognises.
- Gated the only changed call site (`orchestrator.py`): `include_layers = _STANDARD_LAYERS | {"wiki"}` when `state.preferences.wiki_layer` else `None` (D-06 union, D-05 byte-identity).
- Updated the `build_context_prefix` docstring to document that `"wiki"` is opt-in and must be unioned with the standard set.
- Tests: byte-identity regression (`include_layers=None` == no-kwarg on a fully-seeded corpus), the `{"wiki"}`-alone negative control proving standard layers get dropped (documents *why* the union is required), a `_STANDARD_LAYERS`-value guard, and captured-arg orchestrator tests asserting `None` when the flag is off and the exact six-key frozenset when on.

**Task 2 — One-time [semantic]-absent degradation warning (c148fdd)**
- Rewrote the wiki-assembly block to capture `emb = get_embedder(root)` exactly ONCE, reused for both `_semantic_wiki_layer(root, query, emb)` and the warning gate (no second probe).
- Added `_warn_semantic_absent(console)` guarded by a module-level `_semantic_warning_emitted` sentinel — fires at most once per process. Warning text names `pip install flowstate[semantic]`; the `[` of `[semantic]` is escaped so Rich markup renders it literally.
- Gate discriminator is `_semantic is None and (emb is None or not emb.available())` — the same absent-embedder condition, so the warning does not fire for unrelated `None` returns (e.g. missing corpus with a working embedder). Degrades to the static `_read_wiki_layer` fallback; never raises (D-07).
- Tests: warning emitted exactly once across two calls, no warning on the default path, and no-raise when both embedder and corpus are absent.

## Deviations from Plan

None — plan executed exactly as written. One incidental note: Rich markup would have consumed the literal `[semantic]` token as a style tag, so the warning string escapes the opening bracket (`flowstate\[semantic]`) to render it literally; this is an implementation detail of "name the extra," not a scope deviation.

## Verification

- `uv run python -m pytest tests/test_context_prefix.py tests/test_orchestrator.py tests/test_state.py -q` → 112 passed.
- Full suite: **1193 passed, 91.26% coverage** (≥80% gate met).
- `uv run ruff check`/`ruff format` on all touched files → clean.
- D-03 fence: `git diff` on `orchestrator.py` touches only the `_STANDARD_LAYERS` import and the `build_context_prefix` call site — the distill/run_pipeline body is unchanged.

## Requirements Satisfied

- **WIKI-04**: opt-in flag makes the orchestrator fire the wiki layer via the correct standard-union; flag off is byte-identical.
- **WIKI-05**: `[semantic]`-absent path is a one-time-warning no-op naming the extra, never a crash.

## TDD Gate Compliance

Task 1 was marked `tdd="true"` (plan `type: execute`, not `type: tdd`, so no runtime gate fired). RED and GREEN were committed together per task rather than as separate `test(...)`/`feat(...)` commits — the flag, union constant, and their tests are a single coherent behavioral unit. Both tasks landed with passing tests and no regressions.

## Notes for Downstream (Plan 21-03)

The dogfood smoke-test (D-08 / WIKI-06) is still pending — it should distill against this project's real `memory.db`, call `build_context_prefix(..., include_layers=_STANDARD_LAYERS | {"wiki"})`, and assert the wiki layer demonstrably fires (corpus content in the assembled prefix), skipping with a reason if neither semantic nor any corpus can be produced.

## Self-Check: PASSED

- Commits 58d140f, c148fdd verified present in `git log`.
- All six modified files present with the claimed symbols (`wiki_layer`, `_STANDARD_LAYERS`, `_warn_semantic_absent`).
