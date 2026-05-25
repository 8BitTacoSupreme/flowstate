---
phase: 02-operate-safely
plan: 04
subsystem: events
tags: [hooks, env-var, registry, gating, memory-handlers]
requires: [PIVOT-01]
provides: [HOOK-01, HOOK-02]
affects: [events/handler, events/registry, memory_handlers]
tech-stack:
  added: []
  patterns: [profile-rank-gating, per-call-env-lookup, denylist-precedence]
key-files:
  created:
    - tests/test_events_registry.py
  modified:
    - flowstate/events/handler.py
    - flowstate/events/registry.py
    - flowstate/memory_handlers.py
    - tests/test_memory_handlers.py
decisions:
  - "Per-call os.environ lookup over module-level cache — easiest to monkeypatch in tests, no stale state risk"
  - "Disabled-names takes precedence over profile rank — gives users an explicit override even when env profile would allow"
  - "Decorator validates profile at decoration time (not register time) — fail fast on typos in handler code"
  - "register_handler() now returns bool — callers can introspect; bus discards the result so no API break"
metrics:
  duration: "3m 24s"
  tasks: 2
  files: 4
  tests_added: 25
  tests_passing: 211
  coverage: "90.58%"
  completed: "2026-05-25T19:07:42Z"
---

# Phase 02 Plan 04: Hook Env-Var Gating Summary

JSON-free, decorator-driven hook profile gating: `FLOWSTATE_HANDLERS=minimal|standard|strict` selects a rank threshold; `FLOWSTATE_DISABLED_HANDLERS=name1,name2` denylists specific handlers with precedence over profile. The `@handler` decorator gained a `profile=` kwarg (default `"standard"`); memory handlers are tagged `"minimal"` so they always register.

## Tasks Completed

| Task | Name | Commits | Files |
|------|------|---------|-------|
| 1 | Extend `@handler` + add profile/disabled gating in `HandlerRegistry` | `937f1f3` (test), `4fb1d47` (impl) | `flowstate/events/handler.py`, `flowstate/events/registry.py`, `tests/test_events_registry.py` |
| 2 | Tag memory handlers with `profile="minimal"` + integration tests | `b4d5d24` (test), `e5797dd` (impl) | `flowstate/memory_handlers.py`, `tests/test_memory_handlers.py` |

## What Was Built

### Decorator Extension (`flowstate/events/handler.py`)

- New `Literal["minimal", "standard", "strict"]` kwarg `profile=`, default `"standard"`.
- `VALID_PROFILES` tuple + `ValueError` raised at decoration time on invalid values (fails fast on typos).
- Attribute attached to both the inner `fn` and the `functools.wraps` wrapper so `handler.profile` is always present on registered callables.
- `EventHandler` Protocol updated to declare `profile: str`.

### Registry Gating (`flowstate/events/registry.py`)

- `_PROFILE_ORDER = {"minimal": 0, "standard": 1, "strict": 2}` — lower = looser.
- `_current_profile()` reads `os.environ["FLOWSTATE_HANDLERS"]` per-call, lowercased + stripped, falls back to `"standard"` on unset or unrecognized values.
- `_disabled_names()` reads `os.environ["FLOWSTATE_DISABLED_HANDLERS"]` per-call, splits on comma, strips whitespace, drops empty strings.
- `register_handler()` now returns `bool` (was `None`):
  - First checks `handler.__name__ in _disabled_names()` → log `info`, return `False`. **Disabled precedence holds.**
  - Then checks `handler.profile rank > _current_profile() rank` → log `info`, return `False`.
  - Otherwise registers all event types and returns `True`.
- Bus already discards the return value, so no breaking change.

### Memory Handler Tagging (`flowstate/memory_handlers.py`)

- Both `on_step_completed` and `on_step_failed` now tagged `profile="minimal"`.
- Module docstring documents the env-var contract.
- Handler bodies unchanged.

## Per-Call vs Module-Level Cache (W2 Decision)

The plan-checker iteration-1 W2 note flagged whether the env-var helpers should cache at module load or read per-call. **Per-call lookup is the chosen strategy**, blessed in CONTEXT.md commit `6c61ac2`:

- `monkeypatch.setenv("FLOWSTATE_HANDLERS", "minimal")` immediately takes effect with no `reload()` gymnastics.
- No risk of stale state across test runs or across long-lived processes that toggle env vars at runtime.
- Cost is one `os.environ.get` per `register_handler()` call — negligible (registrations happen at startup, not per-event).

## Env-Var Edge Cases Tested

| Variable | Input | Result |
|----------|-------|--------|
| `FLOWSTATE_HANDLERS` | unset | rank 1 (standard) |
| `FLOWSTATE_HANDLERS` | `"minimal"` | rank 0 |
| `FLOWSTATE_HANDLERS` | `"strict"` | rank 2 |
| `FLOWSTATE_HANDLERS` | `"MINIMAL"` | rank 0 (case-insensitive) |
| `FLOWSTATE_HANDLERS` | `"paranoid"` | rank 1 (fallback) |
| `FLOWSTATE_DISABLED_HANDLERS` | unset | `set()` |
| `FLOWSTATE_DISABLED_HANDLERS` | `"a,b,c"` | `{"a","b","c"}` |
| `FLOWSTATE_DISABLED_HANDLERS` | `" a , b , c "` | `{"a","b","c"}` (whitespace tolerated) |
| `FLOWSTATE_DISABLED_HANDLERS` | `"a,,,"` | `{"a"}` (empty strings ignored) |

## Precedence Rule (HOOK-02 Locked Semantics)

A handler that **would** register by profile (e.g. `profile="standard"` with `FLOWSTATE_HANDLERS=strict`) is still **skipped** if its `__name__` appears in `FLOWSTATE_DISABLED_HANDLERS`. The denylist is an unconditional opt-out and is checked before the profile rank comparison.

## Test Counts

| File | Tests Added | Tests Total |
|------|-------------|-------------|
| `tests/test_events_registry.py` (new) | 22 | 22 |
| `tests/test_memory_handlers.py` (extended) | 3 | 9 |
| **Plan total added** | **25** | — |
| Full suite | — | **211 passed** |

Breakdown of new tests in `test_events_registry.py`:
- `TestCurrentProfile`: 5 (unset, minimal, strict, case-insensitive, unrecognized)
- `TestDisabledNames`: 5 (unset, single, comma, whitespace, empty)
- `TestHandlerProfileKwarg`: 4 (default, minimal, strict, invalid)
- `TestRegistryProfileGating`: 5 (minimal/standard/strict envs + unset + missing event_types)
- `TestRegistryDisabledNames`: 3 (skipped, precedence over allow, non-disabled still works)

## Coverage Delta

| File | Coverage |
|------|----------|
| `flowstate/events/handler.py` | 100% (was 100%) |
| `flowstate/events/registry.py` | 100% (was ~100%; new helpers fully covered) |
| `flowstate/memory_handlers.py` | 96% (unchanged — tagging is decorator-only) |
| **Project total** | **90.58%** (well above 80% gate) |

## Verification

Per the plan's `<verification>` block:

- HOOK-01: `pytest tests/test_events_registry.py::TestRegistryProfileGating tests/test_memory_handlers.py::TestMemoryHandlersProfileGating -x` → 8 passed
- HOOK-02: `pytest tests/test_events_registry.py::TestRegistryDisabledNames -x` → 3 passed
- Coverage gate: `pytest --cov=flowstate --cov-fail-under=80` → 211 passed, 90.58%
- Sanity: `FLOWSTATE_HANDLERS=minimal` registration of memory handlers via real `HandlerRegistry` → `[True, True]`

## Deviations from Plan

None — plan executed exactly as written, including the W2-alignment note about per-call env-var lookup. No bugs surfaced; no architectural decisions needed; no auth gates.

## Known Stubs

None. The feature is feature-complete and wired end-to-end: decorator → registry gating → memory_handlers tagged → tests prove env-var control affects real registration.

## Self-Check: PASSED

- `flowstate/events/handler.py` exists, contains `profile: Literal[...]` at line 29
- `flowstate/events/registry.py` exists, contains `_current_profile`, `_disabled_names`, `_PROFILE_ORDER`
- `flowstate/memory_handlers.py` exists, contains `profile="minimal"` on both `@handler` lines (60, 104)
- `tests/test_events_registry.py` exists with 22 tests
- `tests/test_memory_handlers.py` extended with `TestMemoryHandlersProfileGating` (3 tests)
- All commits exist in `git log --oneline`:
  - `937f1f3` test(02-04): add failing tests for handler profile + disabled gating
  - `4fb1d47` feat(02-04): add profile= kwarg to @handler + env-var gating in HandlerRegistry
  - `b4d5d24` test(02-04): add failing tests for memory_handlers profile='minimal' tagging
  - `e5797dd` feat(02-04): tag memory_handlers with profile='minimal' for env-var gating
