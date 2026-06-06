---
phase: 03-ingredients-pack-canon-fixtures
plan: "02"
subsystem: bridge
tags: [canon, bridge, system-prompt, cag, inject_canon]
dependency_graph:
  requires: []
  provides: [CANON constant, BridgeConfig.inject_canon, canon prepend in run()]
  affects: [flowstate/bridge.py, tests/test_bridge.py]
tech_stack:
  added: []
  patterns: [module-level constant, dataclass field default, conditional system-prompt assembly]
key_files:
  modified:
    - flowstate/bridge.py
    - tests/test_bridge.py
decisions:
  - "CANON constant placed before _SENTINEL at module level; inject_canon=True is default so every invocation is covered without caller opt-in"
  - "final_system.strip() guard ensures --system-prompt is not emitted when both inject_canon=False and no system_prompt — matches pre-change contract"
  - "CANON text lifted verbatim from /Users/jhogan/CLAUDE.md §1-4; no paraphrase"
metrics:
  duration: "5m"
  completed_date: "2026-06-06"
  tasks_completed: 1
  files_changed: 2
---

# Phase 3 Plan 02: CANON Constant + inject_canon Field Summary

Ship the Karpathy canon as a `CANON` module constant in `flowstate/bridge.py` and prepend it to every `claude --print` system prompt as the first (most stable) CAG layer, suppressible via `BridgeConfig.inject_canon: bool = True`.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Add CANON constant + inject_canon field + prepend logic | 82dcd68 | flowstate/bridge.py, tests/test_bridge.py |

## What Was Built

### flowstate/bridge.py

- **`CANON` module constant** — added after the module docstring, before `_SENTINEL`. Multi-line triple-quoted string containing §1-4 of `/Users/jhogan/CLAUDE.md` verbatim: Think Before Coding, Simplicity First, Surgical Changes, Goal-Driven Execution.
- **`BridgeConfig.inject_canon: bool = True`** — new field added immediately after `effort`. Defaults to `True` so all existing callers get canon injection without any code changes.
- **System-prompt prepend logic in `run()`** — replaced the old `if system_prompt: cmd.extend(...)` block with:
  1. Compute `canon_prefix = CANON + "\n\n"` when `inject_canon=True`, else `""`
  2. `final_system = canon_prefix + (system_prompt or "")`
  3. Emit `--system-prompt final_system` only when `final_system.strip()` is non-empty

### tests/test_bridge.py

Added `TestCanonInjection` class with 5 tests:
- `test_inject_canon_true_prepends_canon_before_system_prompt` — CANON appears before caller's system_prompt in the emitted command
- `test_inject_canon_true_no_system_prompt_emits_canon` — `--system-prompt` is still emitted (carrying CANON alone) even when no caller system_prompt is passed
- `test_inject_canon_false_omits_canon` — CANON text absent from emitted command
- `test_inject_canon_false_no_system_prompt_no_flag` — `--system-prompt` not emitted at all when `inject_canon=False` and no system_prompt
- `test_canon_constant_is_nonempty` — validates all four section headings are present in `CANON`

## Deviations from Plan

None — plan executed exactly as written.

Ruff auto-formatted the shell script string in `_make_echo_bridge` from single-quote to double-quote style; this is expected pre-commit hook behavior, not a deviation.

## Verification

```
CANON constant:      grep -c '^CANON = ' flowstate/bridge.py → 1 ✓
inject_canon field:  'inject_canon: bool = True' in BridgeConfig ✓
run() usage count:   grep -v '^#' flowstate/bridge.py | grep -c inject_canon → 2 ✓
TestCanonInjection:  class present with inject_canon=True and inject_canon=False assertions ✓
test_bridge.py:      python -m pytest tests/test_bridge.py -x -q → 17 passed ✓
full suite + cov:    python -m pytest tests/ --cov=flowstate --cov-fail-under=80 -q → 322 passed, 91.54% coverage ✓
ruff:                ruff check flowstate/bridge.py → All checks passed ✓
```

## Self-Check: PASSED

- `flowstate/bridge.py` exists and contains `CANON =` at module level: FOUND
- `tests/test_bridge.py` exists and contains `TestCanonInjection`: FOUND
- Commit 82dcd68 exists: FOUND
