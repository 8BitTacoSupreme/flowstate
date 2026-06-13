---
phase: quick-260613-ga5
plan: "01"
status: complete
subsystem: bench/context_prefix
tags: [bench, context-prefix, paired-design, include_layers, cohens-d]
requirements: [GA5-LAYERS, GA5-PAIRED]
key-files:
  created:
    - tests/test_bench_replicate.py
  modified:
    - flowstate/context_prefix.py
    - tests/test_context_prefix.py
    - bench/compound_eval.py
    - tests/test_bench_judge.py
    - bench/replicate.py
decisions:
  - "include_layers gated at assembly time (not by post-hoc string split) — each layer helper is conditionally invoked; default path (None) is byte-identical"
  - "_run_one non-full arms wrap build_context_prefix with setdefault(include_layers=include) in try/finally — restores original unconditionally"
  - "replicate computes both raw and paired aggregates always; metric driving Cohen's d is selected at reporting time via --paired flag"
metrics:
  duration: ~12m
  completed: "2026-06-13"
  tasks: 3
  files: 5
---

# Phase quick-260613-ga5 Plan 01: Per-Layer Context-Prefix Toggle + Paired-Design Bench Wiring

**One-liner:** Assembly-time `include_layers` kwarg on `build_context_prefix` + `--layers` arm wiring through `compound_eval` + multi-arm `--paired` normalization with per-arm Cohen's d in `replicate`.

## Tasks Completed

| # | Name | Commit | Files |
|---|------|--------|-------|
| 1 | Add include_layers assembly-time gating to build_context_prefix | `0256eee` | flowstate/context_prefix.py, tests/test_context_prefix.py |
| 2 | Replace --inject with --layers in compound_eval, per-arm tests | `d1fd243` | bench/compound_eval.py, tests/test_bench_judge.py |
| 3 | Multi-arm loop + --paired normalization + per-arm Cohen's d in replicate | `2908607` | bench/replicate.py, tests/test_bench_replicate.py |

## What Was Built

### Task 1 — `include_layers` in `build_context_prefix`

Added `include_layers: frozenset[str] | None = None` as an additive keyword-only parameter after `budget_tokens`. An `_included(key)` local helper returns `True` when `include_layers is None or key in include_layers`.

Each of the five layer builds is guarded:
- `fixtures_layer = _read_fixtures_layer(root) if _included("fixtures") else ""`
- `gotchas_layer = _read_gotchas_layer(root, memory) if _included("gotchas") else ""`
- `memory_layer = (memory.get_context(query) if query else "") if _included("memory") else ""`
- `since_last_run_layer = _read_since_last_run_layer(root, memory) if _included("since_last_run") else ""`
- pack block: `if pack_exists and _included("pack"):` — the fit-ladder is never invoked for excluded pack

Default path (`include_layers=None`) is byte-identical to the no-kwarg call.

Four new tests: `test_include_layers_none_is_byte_identical`, `test_include_layers_pack_only_excludes_compounding`, `test_include_layers_memory_only_excludes_pack_and_fixtures`, `test_include_layers_empty_frozenset_returns_empty`.

### Task 2 — `--layers` in `compound_eval`

Added `_LAYERS_MAP` module-level dict mapping the four layer choices to `frozenset[str] | None`:
- `"full" -> None` (no patch)
- `"none" -> frozenset()` (empty prefix — old inject=off)
- `"pack" -> frozenset({"fixtures", "pack"})`
- `"memory" -> frozenset({"gotchas", "memory", "since_last_run"})`

Removed `--inject`; added `--layers` with the four choices (default `full`). Rewrote `_run_one(root, *, dry_run, layers="full")`: `full` calls `run_pipeline` directly; non-full arms install a wrapper that calls the original `build_context_prefix` with `k.setdefault("include_layers", include)` in try/finally.

Updated `_real_loop` (inject param → layers) and `main()` (layers=args.layers). `_cheap_loop` unchanged (defaults layers="full").

Four new per-arm tests plus updated legacy test (inject=False → layers="none").

### Task 3 — `--paired` + multi-arm + per-arm Cohen's d in `replicate`

- Renamed `_run_trial(inject, ...)` to `_run_trial(arm, ...)` — uses `--layers arm` instead of `--inject inject`.
- Added `_paired_normalize(trials)`: subtracts `t[0]` from each element in each trajectory; translation-invariant (improvement = last−first unchanged).
- Added `--layers nargs+` (default all four arms) and `--paired` flag.
- `summary["arms"][arm]` contains both `"raw"` and `"paired"` aggregates for every arm.
- `summary["effect_size_cohens_d"]` = per non-none arm vs `none`, on `"paired"` metric when `--paired` else `"raw"`.
- `summary["improvement_delta_vs_none"]` = per-arm `{raw: ..., paired: ...}` delta.
- New file `tests/test_bench_replicate.py`: 10 pure-helper unit tests covering `_paired_normalize`, `_agg`, and `_cohens_d`.

## Verification

```
pytest tests/ --cov=flowstate --cov-fail-under=80
  622 passed, 4 warnings
  Total coverage: 92.33% (>= 80% gate)

ruff check flowstate/ bench/ tests/   → All checks passed
ruff format --check flowstate/ bench/ tests/ → 69 files already formatted
```

## Deviations from Plan

None — plan executed exactly as written. The design override (assembly-time gating, not post-hoc string split) was already specified in the plan objective and was followed faithfully.

## Known Stubs

None.

## Threat Flags

None. Changes are internal to the bench research harness and the context_prefix assembler. No new network endpoints, auth paths, or schema changes.
