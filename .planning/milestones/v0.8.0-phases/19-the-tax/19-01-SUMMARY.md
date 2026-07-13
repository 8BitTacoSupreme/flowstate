---
phase: 19-the-tax
plan: 01
status: complete
subsystem: bridge
tags: [claude-cli, usage-accounting, tokens, latency, json-output]

# Dependency graph
requires:
  - phase: v0.2 (ClaudeBridge)
    provides: "ClaudeBridge.run() with output_format='json' flag already wired but unparsed"
provides:
  - "BridgeUsage dataclass (tokens_in/tokens_out/cache_read)"
  - "BridgeResult.usage + BridgeResult.duration_s"
  - "ClaudeBridge cumulative totals (total_tokens_in/out/cache_read/total_wall_clock_s)"
affects: [19-02, RunSnapshot, bench/report.py, orchestrator]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Never-raise json parse guard around subprocess stdout (try/except → usage=None fallback)"
    - "Instance-level cumulative accounting via a single _accumulate() fold point"

key-files:
  created: []
  modified:
    - flowstate/bridge.py
    - tests/test_bridge.py

key-decisions:
  - "Append usage/duration_s after existing BridgeResult fields to preserve positional construction of all existing callers"
  - "Parse only when output_format=='json' AND a top-level `result` key is present; anything else falls back to raw stdout with usage=None (never raises)"
  - "Accumulate only on successful returns — dry-run, error, and timeout returns measure no real work and contribute nothing"

patterns-established:
  - "Tampering-boundary guard (T-19-01): json.loads of subprocess stdout is wrapped so malformed/absent output degrades to usage=None and byte-identical raw stdout"

requirements-completed: [TAX-01]

# Metrics
duration: 18min
completed: 2026-07-11
---

# Phase 19 Plan 01: The Tax — BridgeResult usage/duration accounting Summary

**`ClaudeBridge.run()` now captures the real token (`input`/`output`/`cache_read`) and wall-clock usage that the `--output-format json` path already returned but discarded, exposing it per-call via `BridgeResult.usage`/`.duration_s` and cumulatively on the bridge instance — with text-mode `.output` byte-identical and malformed json guarded.**

## Performance

- **Duration:** ~18 min
- **Tasks:** 2/2
- **Files modified:** 2 (`flowstate/bridge.py`, `tests/test_bridge.py`)
- **Tests:** 1120 passed, 91.17% coverage (bridge file: 12 new tests, 31 total)

## Accomplishments

- **Task 1 — usage + duration_s:** Added a frozen `BridgeUsage(tokens_in, tokens_out, cache_read)` dataclass and two appended `BridgeResult` fields (`usage: BridgeUsage | None`, `duration_s: float | None`). A `time.monotonic()` window around `subprocess.run()` populates `duration_s` on every non-dry, non-error return. On the json path, `result.stdout` is parsed inside a try/except: a well-formed object with a top-level `result` key yields that string as `.output` plus a `BridgeUsage` built from `usage.input_tokens/output_tokens/cache_read_input_tokens` (missing sub-keys → 0); any parse failure or absent `result` key leaves `.output` as raw stdout and `usage=None`. Text mode is unchanged and byte-identical.
- **Task 2 — cumulative totals:** `ClaudeBridge.__init__` seeds `total_tokens_in/total_tokens_out/total_cache_read` (int 0) and `total_wall_clock_s` (float 0.0). A single private `_accumulate(result)` fold, called from the success return, adds each successful call's duration and (when present) usage into the instance totals. Text-mode calls add only wall clock; error/timeout returns add nothing. This is the single read point Plan 02 consumes from the shared pipeline bridge.

## Verification

- `uv run python -m pytest tests/test_bridge.py` — 31 passed.
- `uv run python -m pytest` (full suite) — 1120 passed, coverage 91.17% (≥80% gate met).
- `uv run ruff check flowstate/bridge.py` — clean.

## TDD Gate Compliance

Both tasks followed RED → GREEN. Gate commits present in git log:
- RED: `5819da7 test(19-01): add failing usage/duration + cumulative-totals tests`
- GREEN (Task 1): `d9f8e5d feat(19-01): capture real usage + duration_s in BridgeResult via json path`
- GREEN (Task 2): `5a18a05 feat(19-01): accumulate cumulative usage + wall-clock totals on ClaudeBridge`

## Deviations from Plan

None — plan executed exactly as written. (Minor honoring of the behavior spec over the terse action text: `_accumulate` is gated on `result.success` so a completed-but-nonzero-returncode call contributes nothing, matching the "error returns contribute nothing" behavior clause.)

## Threat Surface

- **T-19-01 (Tampering, mitigated):** json parse of untrusted-shaped subprocess stdout is wrapped in try/except catching `JSONDecodeError/ValueError/TypeError`; malformed or non-dict output and absent `result` keys degrade to `usage=None` + raw stdout, preserving the never-raise/`success` contract.
- **T-19-SC:** No new packages introduced (stdlib `json`/`time` only).

No new threat surface beyond the plan's registered boundary.

## Notes for Plan 02

- Read consumption off the **shared pipeline bridge** instance (`orchestrator._make_bridge` creates one per pipeline): `bridge.total_tokens_in`, `total_tokens_out`, `total_cache_read`, `total_wall_clock_s`.
- Callers must pass `output_format="json"` to get per-call `usage`; the default text path keeps `usage=None` (byte-identical output, no regression).

## Self-Check: PASSED

- `flowstate/bridge.py` — FOUND (BridgeUsage + fields + totals present)
- `tests/test_bridge.py` — FOUND (12 new tests)
- Commits 5819da7, d9f8e5d, 5a18a05 — FOUND in git log
