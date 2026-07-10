---
phase: 15-bundle-gsd
plan: 03
subsystem: launcher
status: complete
tags: [launcher, gsd, detect-neutralize, unconditional-handoff]
requires:
  - flowstate.installer.install_gsd (15-02 — GSD is installed unconditionally, so detection is moot)
provides:
  - flowstate.launcher.detect_tools always reports gsd available (no .planning marker gate)
  - flowstate launch gsd <N> emits a working handoff unconditionally
affects:
  - 15-04 (refresh path assumes GSD always present)
tech-stack:
  added: []
  patterns: [always-present-tool, fixed-literal-handoff, surgical-branch-removal]
key-files:
  created: []
  modified:
    - flowstate/launcher.py
    - tests/test_launcher.py
decisions:
  - "GSD is hardwired available in detect_tools (results = {'gsd': True}) rather than dropped entirely — keeps gsd first in the tool-availability display order and the detect_tools contract intact for print_next_steps."
  - "The .planning marker proxy and the 'GSD not detected, run /gsd:new-project' else-branch are both removed; the gsd launch handoff is now offered unconditionally (T-15-09 accept: GSD guaranteed present by the installer)."
  - "_SKILL_HANDOFFS strategy/discipline namespace gating left untouched — those correctly stay gated on installed .claude/skills/<namespace> (T-14-12)."
  - "Handoff strings stay fixed literals (/gsd:plan-phase {N}, /gsd:progress); no vendored content is interpolated into the emitted command (T-15-08 mitigate)."
metrics:
  duration: ~8 min
  completed: 2026-07-10
---

# Phase 15 Plan 03: Neutralize the Launcher GSD Detect-and-Suggest Path Summary

`flowstate launch gsd <N>` now produces a working `/gsd:plan-phase {N}` handoff unconditionally. The launcher's GSD detect-and-suggest path is gone: the `.planning` marker proxy that gated GSD availability and the `print_next_steps` "GSD not detected. Run /gsd:new-project in a Claude Code session." else-branch are both removed. GSD is treated as always present because FlowState vendors and installs it (15-01/15-02).

## What Was Built

**Task 1 — Remove the GSD detect-and-suggest path (commit `e9bbb3c`, TDD)**

`flowstate/launcher.py`:
- `TOOL_MARKERS` drops its `"gsd": [".planning"]` entry; only `strategy`/`discipline` (built-in, empty markers) remain.
- `detect_tools` seeds `results = {"gsd": True}` up front (preserving gsd-first display order) and removes the `gsd_skills = (root / ".planning").exists()` proxy. GSD is always reported available.
- `print_next_steps` drops the `if tools.get("gsd") / else` conditional and always prints `flowstate launch gsd 1 — Plan phase 1 with GSD`.
- `launch_command` / `_gsd_command` are unchanged — they already produce the `/gsd:plan-phase {N}` and `/gsd:progress` fixed literals.
- `_SKILL_HANDOFFS` strategy/discipline gating is untouched.

`tests/test_launcher.py`: replaced the old detect-gated assertions. `test_no_tools` (which asserted `not tools["gsd"]`) became `test_builtin_tools_available` + `test_gsd_always_available`; `test_gsd_detected` became `test_gsd_available_with_planning`. Added `test_gsd_fresh_project_no_planning` (handoff works, no "not detected"/"new-project" text) and a new `TestPrintNextSteps::test_no_gsd_not_detected_branch` that captures `launcher.console` output and asserts the "not detected"/"new-project" suggestion is gone and `flowstate launch gsd 1` is present.

## TDD Gate Compliance

RED verified before implementation: `test_gsd_always_available` failed with `assert tools["gsd"]` → `assert False` against the old `.planning`-gated code. GREEN after the launcher edit: all 15 launcher tests pass. (RED and GREEN are combined into one atomic commit `e9bbb3c` because the two files are tightly coupled and the plan is a single task.)

## Verification

- `flowstate launch gsd 1` → contains `/gsd:plan-phase 1`, no "not detected" branch (test).
- Fresh project with no `.planning` → `detect_tools` reports gsd available; handoff works (test).
- `print_next_steps` for a no-`.planning` project emits no "new-project" suggestion (captured-output test).
- strategy/discipline handoffs remain namespace-gated (`test_launcher_skills.py` unchanged, still passing).
- Full suite: 1017 passed, coverage 91.62% (≥80% gate).

## Deviations from Plan

None — plan executed exactly as written.

## Threat Surface

No new surface. Handoff strings remain fixed literals (T-15-08 mitigated); assumed-present GSD is the intended design guaranteed by the 15-02 installer (T-15-09 accepted).

## Self-Check: PASSED

- `flowstate/launcher.py` — modified, present.
- `tests/test_launcher.py` — modified, present.
- Commit `e9bbb3c` — present in git log.
