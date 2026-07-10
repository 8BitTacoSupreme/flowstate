---
phase: 14-vendor-surface
plan: 04
subsystem: launcher
status: complete
tags: [launcher, cli, vend-04, vend-05, skills, handoff, gating, tdd, docs]
requires: [VEND-04, VEND-05]
provides:
  - "flowstate launch strategy → gstack /office-hours handoff (gated on installed skills)"
  - "flowstate launch discipline → superpowers test-driven-development handoff (gated)"
  - "install-skills prompt when the vendored namespace is absent (no broken command)"
  - "discipline added to the launch CLI Choice"
  - "README test count reconciled to the true post-phase total (1000)"
affects: [flowstate/launcher.py, flowstate/cli.py, tests/test_launcher_skills.py, tests/test_launcher.py, README.md]
tech-stack:
  added: []
  patterns:
    - "_SKILL_HANDOFFS dict (tool → (namespace, fixed-literal handoff)) — Phase 15 extends by adding entries"
    - "_skill_installed(root, namespace) single presence gate on .claude/skills/<namespace>"
    - "fixed-literal handoff strings, no interpolation of vendored content (T-14-13)"
key-files:
  created:
    - tests/test_launcher_skills.py
  modified:
    - flowstate/launcher.py
    - flowstate/cli.py
    - tests/test_launcher.py
    - README.md
decisions:
  - "Handoffs built from fixed literals via a _SKILL_HANDOFFS table — launcher only PRINTS, never reads/executes vendored skill files (T-14-13/T-14-14)"
  - "Single _skill_installed gate on .claude/skills/<namespace> presence, extensible for Phase 15 (add a table entry, not new logic)"
  - "When a namespace is absent, return a `flowstate install-skills` prompt (a comment, not a runnable command) rather than a broken/misleading handoff (T-14-12)"
  - "Updated the pre-existing test_launcher.py::test_strategy_command — strategy is now gated, so with no gstack it emits the install prompt, not the old 'flowstate init' string"
  - "README count derived from `pytest --collect-only` (=1000) not hardcoded; never 803/947 (T-14-15)"
metrics:
  duration: ~6 min
  completed: 2026-07-10
requirements: [VEND-04, VEND-05]
---

# Phase 14 Plan 04: Skill-Gated Launch Handoffs + README Reconciliation (VEND-04, VEND-05) Summary

Wired `flowstate launch strategy` to gstack's `/office-hours` and `flowstate launch discipline` to the superpowers `test-driven-development` skill — each surfaced **only** when the vendored namespace is installed under `.claude/skills/`, mirroring the existing `_gsd_command`/`launch_command` handoff shape. When the skills are absent, the launcher prints a `flowstate install-skills` prompt instead of a broken command. `discipline` is now a valid `launch` Choice. As the final Phase-14 plan, it also closed VEND-05: re-derived the true post-phase test count and reconciled README from 985 → 1000.

## What Shipped

**Task 1 — gated handoffs in launcher.py (TDD; test commit `c8495ef`, feat commit `b18fdf1`):**
- Added `_SKILL_HANDOFFS = {"strategy": ("gstack", "/office-hours"), "discipline": ("superpowers", "Use the superpowers test-driven-development skill")}` — a table of `tool → (installed namespace, fixed-literal handoff)`.
- `_skill_installed(root, namespace)` checks `(root / ".claude" / "skills" / namespace).exists()` — the single gate for every vendored handoff; Phase 15 extends the surface by adding a table entry, not new logic.
- `launch_command` short-circuits any tool in `_SKILL_HANDOFFS`: returns `cd {dir} && claude\n  → {handoff}` when installed, else `_install_prompt(namespace)` (a `# … run: flowstate install-skills` comment).
- Handoffs are **fixed literals** — no vendored file content is ever interpolated into the emitted command (T-14-13); the launcher only PRINTS, never reads/executes the skill files (T-14-14).
- `gsd`/`research` behavior unchanged.

**Task 2 — discipline in the launch Choice (commit `d2cf78c`):**
- Extended `@click.argument("tool", type=click.Choice([...]))` to include `"discipline"` (previously rejected with a click usage error).
- Updated the `launch` docstring examples to describe the strategy→/office-hours and discipline→TDD handoffs.

**Task 3 — README test-count reconciliation (commit `5160365`):**
- Re-derived the real collected count via `pytest --collect-only -q` (= **1000**, now that `tests/test_installer.py` from 14-03 and `tests/test_launcher_skills.py` from this plan both exist) and updated README's `tests/` line from 985 → 1000. Number read at runtime, not hardcoded; README contains neither 803 nor 947 (T-14-15).

## Tests

- New `tests/test_launcher_skills.py` (6 tests): office-hours present when gstack installed; TDD present when superpowers installed; install prompt (and NOT the handoff token) when each namespace is absent; discipline gate independent of gstack presence.
- Updated `tests/test_launcher.py::test_strategy_command` for the new gated behavior (install prompt with no skills installed) — a direct consequence of this plan's change, not scope creep.
- Full suite: **1000 passed, 91.77% coverage** (≥80% gate satisfied).

## Verification

- `flowstate launch discipline` (after `install-skills`) → output contains `test-driven-development`, exit 0.
- `flowstate launch strategy` (after `install-skills`) → output contains `office-hours`.
- Both emit `install-skills` guidance when the namespace is absent.
- README `--collect-only` acceptance check: `OK count=1000`; no `803`/`947`.

## Deviations from Plan

**1. [Rule 1 — Bug] Updated pre-existing test_launcher.py::test_strategy_command**
- **Found during:** Task 1 (GREEN)
- **Issue:** The existing test asserted the old `strategy → "flowstate init"` string, which this plan's gating intentionally replaces. Left unchanged it would have failed the full suite.
- **Fix:** Re-pointed the assertion to the new gated behavior (`install-skills` prompt when no gstack skills present).
- **Files modified:** tests/test_launcher.py
- **Commit:** b18fdf1

## Known Stubs

None — both handoffs are wired to real installed-skill detection; no placeholder data.

## Self-Check: PASSED
- tests/test_launcher_skills.py — FOUND
- flowstate/launcher.py, flowstate/cli.py, README.md — modified and committed
- Commits c8495ef, b18fdf1, d2cf78c, 5160365 — all present in git log
