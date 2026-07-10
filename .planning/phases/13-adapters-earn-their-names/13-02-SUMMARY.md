---
phase: 13-adapters-earn-their-names
plan: 02
status: complete
subsystem: tool-adapters
tags: [strategy, rubric, mechanism, honesty, gstack]

# Dependency graph
requires:
  - phase: 12-honesty-failure-capability (plan 02)  # HON-04 success=False failure shape
provides:
  - "strategy.pressure_test() emits and validates a scored rubric (5 dims 0-10 + ship/pivot/kill verdict)"
  - "_parse_rubric(): regex-only rubric parser over untrusted model output"
  - "unparseable/missing rubric -> ToolResult(success=False) via HON-04, no artifact written"
affects: [orchestrator, 14-vendor-work]

tech-stack:
  added: []
  patterns:
    - "Mechanism-over-passthrough: an adapter validates a machine-checkable artifact before reporting success"
    - "Regex-only parse of untrusted LLM output with per-key allow-list + range/membership validation (no eval/exec/literal_eval/json)"

key-files:
  created:
    - tests/test_strategy_rubric.py
  modified:
    - flowstate/tools/strategy.py

decisions:
  - "_parse_rubric scans the whole output (tolerant) rather than requiring a fenced block, but validates strictly: all five _RUBRIC_DIMENSIONS present as ints in 0-10 AND a verdict in _VERDICTS, else None"
  - "Dimension regex uses \\d+ then range-checks (not \\d{1,2}) so '100' fails validation instead of silently truncating to '10'"
  - "Verdict regex is bounded with \\b(ship|pivot|kill)\\b so 'shipping'/'maybe' do not match; case-insensitive, normalized to lowercase"
  - "On success the raw br.output is preserved and a normalized '## Rubric' section is appended; ToolResult.output reports the verdict + score summary"
  - "STRATEGY_SYSTEM_PROMPT is extended statically to require the appended rubric block — no runtime prompt self-modification (PROJECT.md decision honored)"
  - "MOCK_STRATEGY and the if self.dry_run branch are byte-identical to the pre-change version"

requirements-completed: [MECH-02]

metrics:
  duration: ~10 min
  completed: 2026-07-10
---

# Phase 13 Plan 02: Strategy Scored Rubric Summary

**The strategy adapter now enforces Gstack's core mechanism — a machine-checkable scored review. The bridge call must emit parseable per-dimension scores (0-10) across the five evaluation dimensions plus a ship/pivot/kill verdict; `_parse_rubric` validates it with regex only, and an unparseable or missing rubric is surfaced as `ToolResult(success=False)` via the Phase 12 HON-04 path rather than being written as a weak artifact.**

## What Changed

- `flowstate/tools/strategy.py`:
  - Added module constants `_RUBRIC_DIMENSIONS = ("problem_clarity", "ten_x_potential", "feasibility", "risk", "recommendation")` and `_VERDICTS = ("ship", "pivot", "kill")`.
  - Added `_parse_rubric(output) -> tuple[dict[str, int], str] | None`: per-dimension `re.search` with an allow-list of known keys, integer 0-10 range validation, and a bounded verdict membership check. Returns `(scores, verdict)` only when all five dimensions and a valid verdict are present; otherwise `None`. No `eval`/`exec`/`literal_eval`/`json` over model text.
  - Extended `STRATEGY_SYSTEM_PROMPT` (statically) to instruct the model to append a fenced ```rubric block after its prose.
  - `pressure_test()`: after a successful non-empty bridge call, parses the rubric. `None` -> `ToolResult(success=False, error="unparseable rubric: ...", artifacts=[])` and writes no `strategy.md`. Valid -> writes `br.output` plus a normalized `## Rubric` section and returns `success=True` with the verdict + scores in `output`.
  - The empty/failed-bridge branch and the `if self.dry_run` / `MOCK_STRATEGY` paths are unchanged.
- `tests/test_strategy_rubric.py` (new, offline): `_parse_rubric` valid + case-insensitive verdict + four invalid cases (missing dimension, out-of-range score, invalid verdict, no rubric block); `pressure_test` success integration (writes strategy.md, success True, verdict in output) and unparseable-failure integration (success False, no strategy.md written); dry-run golden assertion against `MOCK_STRATEGY.format(...)`. All drive a `MagicMock`/`dry_run` bridge — no live CLI or network.

## Threat Model Coverage

- **T-13-04 (Tampering, rubric parse):** mitigated — regex-only extraction with per-dimension key allow-list, 0-10 range validation, and verdict membership check; malformed input yields `None` (never a crash, never a fake pass).
- **T-13-05 (Repudiation, weak-rubric success):** mitigated — unparseable/missing rubric returns `success=False` and writes no artifact; a bad review cannot be recorded as a passed one.
- **T-13-SC (installs):** accepted — stdlib `re` only, no new runtime deps.

## Deviations from Plan

**1. [Rule 1 - Bug] Reworded a docstring to keep the acceptance grep clean**
- **Found during:** Task 1 verification.
- **Issue:** The `_parse_rubric` docstring listed "eval/exec/literal_eval/json" as forbidden, which tripped the plan's `grep -n "eval(\|exec(\|literal_eval"` acceptance check on the `literal_eval` token.
- **Fix:** Reworded to "no dynamic evaluation of untrusted model text"; grep now returns no matches. No behavior change.
- **Files modified:** flowstate/tools/strategy.py
- **Commit:** 7687127

Otherwise executed as written.

## Verification

- `python -m pytest tests/test_strategy_rubric.py tests/test_tools.py -q` — pass.
- `python -m pytest tests/ --cov=flowstate --cov-fail-under=80 -q` — 968 passed, total coverage 92.24% (strategy.py 100%).
- `grep -n "eval(\|exec(\|literal_eval" flowstate/tools/strategy.py` — no matches.
- `ruff check` / `ruff format --check` — clean on both changed files.
- `--dry-run` strategy artifact is byte-identical to `MOCK_STRATEGY.format(...)` (golden test).

## Task Commits

1. **Task 1: scored-rubric parse + verdict validation (MECH-02)** — `7687127` (feat)
2. **Task 2: offline tests for parse/verdict/failure/MOCK invariance** — `1aa278e` (test)

## Self-Check: PASSED
- FOUND: flowstate/tools/strategy.py (`_parse_rubric`, constants)
- FOUND: tests/test_strategy_rubric.py
- FOUND commit: 7687127
- FOUND commit: 1aa278e
</content>
</invoke>
