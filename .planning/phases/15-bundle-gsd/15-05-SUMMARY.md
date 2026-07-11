---
status: complete
phase: 15-bundle-gsd
plan: 05
subsystem: docs
tags: [readme, gsd, documentation, reconciliation]
requires: [GSD-01, GSD-02, GSD-03, GSD-04]
provides: [GSD-05]
affects: [README.md]
tech-stack:
  added: []
  patterns: [docs-reconciled-to-shipped-code]
key-files:
  created: []
  modified:
    - README.md
decisions:
  - "README test count re-derived from pytest --collect-only post-phase = 1045 (never hardcoded 803/947/1000)"
  - "GSD framing changed from delegate-only to vendored-and-auto-installed; gsd-sdk zero-install claim scoped to the offline query path, session-spawn attributed to the user's own claude"
metrics:
  duration: ~6min
  completed: 2026-07-11
  tasks: 1
  files: 1
---

# Phase 15 Plan 05: README Reconciliation to Bundled-GSD Reality Summary

Reconciled every GSD claim in `README.md` to the bundled-and-auto-installed reality shipped by Plans 15-01 through 15-04, and set the test count to the true post-phase collection total (1045).

## What Was Done

**Task 1 — Reconcile README to bundled GSD + true test count** (commit `22befbd`):

- **Prerequisites:** Removed the `GSD (optional, for Management phase) — gsd-build/gsd-2` bullet. Replaced with a "**GSD is bundled**" note: FlowState vendors GSD ([gsd-build/get-shit-done](https://github.com/gsd-build/get-shit-done), MIT © Lex Christopherson) and installs it unconditionally into `.claude/`, `gsd-sdk` works zero-install (bundled `node_modules`, query path runs fully offline), and agent-session spawning uses the user's own `claude` CLI.
- **Acknowledgments:** Rewrote the GSD entry from the delegate-only framing ("FlowState generates the context files GSD consumes … hand off to native GSD execution") to the vendored-and-auto-installed framing, keeping the MIT attribution (© Lex Christopherson). Fixed the stale URL `gsd-build/gsd-2` → `gsd-build/get-shit-done`.
- **Test count:** Re-derived via `uv run --frozen python -m pytest --collect-only -q` → **1045 tests collected**. Updated the one README occurrence (`tests/ # 1000 tests, 92% coverage` → `1045 tests`).

## Verification

Plan automated verify passed:
```
! grep -n "gsd-2" README.md && ! grep -iq "gsd.*install separately|install separately.*gsd" README.md && grep -q "get-shit-done" README.md
→ VERIFY_PASS
```
- `grep -c "vendors" README.md` → 2 (must-have artifact `contains: "vendors"` satisfied)
- `grep -n "1045" README.md` → present; no `1000`/`947`/`803` test-count strings remain
- Pre-commit hooks passed (ruff/pytest skipped — no Python files changed).

Claims were traced to shipped code before writing:
- `flowstate/vendor/gsd/VERSION`: `get-shit-done-cc@1.42.3`, MIT © Lex Christopherson; platform binary EXCLUDED (`--omit=optional`) — "agent-session spawning falls back to the user's own `claude`" is verbatim the vendored provenance note.
- `flowstate/installer.py`: `install_skills` lays down the runtime + full `node_modules` unconditionally so `gsd-sdk` resolves deps by walking up (zero-install query path).

## Deviations from Plan

None — plan executed exactly as written. Single task, single file, no code changes beyond README.

## Threat Surface

No new security-relevant surface. T-15-15 (stale/false README claims) mitigated: test count re-derived from `--collect-only`, every GSD claim traced to shipped code. T-15-16 (attribution) mitigated: MIT attribution (© Lex Christopherson) and canonical `gsd-build/get-shit-done` URL retained.

## Self-Check: PASSED

- FOUND: README.md (modified, committed `22befbd`)
- FOUND: commit `22befbd` in git log
- FOUND: `.planning/phases/15-bundle-gsd/15-05-SUMMARY.md`
