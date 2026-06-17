---
status: complete
quick_id: 260616-x15
title: Expose enable_prompt_caching_1h preference; wire through _make_bridge
date: 2026-06-17
commit: 3ee0d29
---

# Quick Task 260616-x15 — 1h prompt-cache preference

## What
- `flowstate/state.py`: added `enable_prompt_caching_1h: bool = True` to `ProjectPreferences`
  (additive optional field; existing `flowstate.json` loads with the default — no migration bump).
- `flowstate/orchestrator.py`: `_make_bridge` now threads `preferences.enable_prompt_caching_1h`
  into `BridgeConfig` unconditionally (False is meaningful — opt out). `bridge.py` already injects
  `ENABLE_PROMPT_CACHING_1H=1` when the flag is set, so no bridge change was needed.

## Why
The pipeline's Context Generation rewrites config each run and pipeline steps (research can take
minutes) often exceed the 5-min default prompt-cache TTL, evicting the cache between steps. The 1h
TTL (now default-on, configurable) keeps cross-step cache hits. Trades higher 1h cache-write cost
for retention on eligible API-key accounts; harmless no-op otherwise.

## Tests
- `tests/test_state.py`: default True; roundtrip False; legacy flowstate.json without the field
  loads with default True.
- `tests/test_orchestrator.py`: `_make_bridge` reflects True/False; None preferences leaves
  BridgeConfig default (False).

## Gate
670 passed, coverage 92.42% (≥80), ruff check + format clean.

## Note
The gsd-executor died on an API socket error mid-run (no commit/SUMMARY, source change not yet
applied; tests were written). Recovered manually: salvaged the executor's tests, completed the
2-line source change, verified full suite, committed.
