---
phase: 25-confinement-verification
plan: 01
subsystem: infra
tags: [sandbox, confinement, bwrap, sandbox-exec, fail-loud, security]

# Dependency graph
requires:
  - phase: 23-linux-parity-core-seam
    provides: "flowstate/sandbox.py's wrap()/_wrap_macos/_wrap_linux confine dispatch and profile builders"
  - phase: 24-thread-the-seam-config
    provides: "the ProjectPreferences.sandbox tier threaded through bridge.py/gsd_vendor.py call sites"
provides:
  - "SandboxUnavailableError — fail-loud confine dispatch when no confinement is achievable"
  - "wrap()'s confine tier raises on unsupported platforms, absent bwrap, and missing sandbox-exec"
  - "documented (not fixed) WR-2 npm *_TOKEN observe-scrub limitation"
affects: [25-02, 25-03, 25-04, bridge.py-confine-wiring]

# Tech tracking
tech-stack:
  added: []
  patterns: ["fail-loud exception scoped to a single dispatch seam, not scattered across degrade sites"]

key-files:
  created: []
  modified:
    - flowstate/sandbox.py
    - tests/test_sandbox.py
    - flowstate/gsd_vendor.py

key-decisions:
  - "D-01/SBX-06: confine raises SandboxUnavailableError when NO confinement is achievable; observe is completely untouched and never raises; partial capability (bwrap present, landlock absent) still degrades RUNG-1->RUNG-2 within confinement without raising"
  - "Reused check_bwrap_available() (functional smoke test) for the Linux raise decision, not a bare shutil.which, per 25-CONTEXT.md guidance (Ubuntu 24.04 AppArmor blocks bwrap even when the binary exists)"
  - "D-04: WR-2 npm *_TOKEN scrub limitation documented at both gsd_vendor.py wrap sites and in _scrub_env's docstring; exemption set NOT widened"

patterns-established:
  - "SandboxUnavailableError(RuntimeError) is the project's first custom exception class — a single-purpose, non-hierarchical addition to the otherwise-stdlib-exception house style"

requirements-completed: [SBX-06]

# Metrics
duration: 12min
completed: 2026-07-12
---

# Phase 25 Plan 01: Fail-Loud Confine Dispatch Summary

**`wrap(tier="confine")` now raises `SandboxUnavailableError` with a per-platform install hint instead of silently running unconfined, while `observe` and partial-capability (bwrap-only RUNG-2) degrades stay untouched.**

## Performance

- **Duration:** ~12 min
- **Started:** 2026-07-12T19:25:00-04:00
- **Completed:** 2026-07-12T19:37:00-04:00
- **Tasks:** 3
- **Files modified:** 3 (`flowstate/sandbox.py`, `tests/test_sandbox.py`, `flowstate/gsd_vendor.py`)

## Accomplishments
- `SandboxUnavailableError(RuntimeError)` added — the project's first custom exception class, scoped narrowly to the confine-dispatch fail-loud seam
- `wrap()`'s confine dispatch raises on unsupported platforms (was: silent scrubbed passthrough)
- `_wrap_macos` verifies the located `sandbox-exec` binary is a real file before dispatching (was: trusted the `/usr/bin/sandbox-exec` guess blindly)
- `_wrap_linux`'s RUNG-3 (bwrap fully unavailable) now raises instead of printing a warning and degrading to observe; RUNG-1/RUNG-2 (landlock present/absent) degrade unchanged, no raise
- Module docstring and `wrap()`/`_wrap_linux` docstrings re-scoped: the "never fails" guarantee now explicitly applies to `observe` + the availability probes only
- WR-2 (npm `*_TOKEN` scrub limitation) documented at both `gsd_vendor.py` wrap sites and in `_scrub_env`'s docstring, per D-04 — not fixed, exemption set unchanged

## Task Commits

Each task was committed atomically (Task 1 followed RED/GREEN TDD):

1. **Task 1 RED: failing tests for fail-loud confine dispatch** - `66de40d` (test)
2. **Task 1 GREEN: fail-loud confine dispatch + SandboxUnavailableError** - `b56cbdf` (feat)
3. **Task 2: rewrite TestWrapLinux fallback tests for the fail-loud contract** - `e8d39dc` (test)
4. **Task 3: document the WR-2 npm *_TOKEN scrub limitation (D-04)** - `e0c4133` (docs)

**Plan metadata:** (this commit, SUMMARY.md + REQUIREMENTS.md)

## Files Created/Modified
- `flowstate/sandbox.py` - `SandboxUnavailableError`, fail-loud confine dispatch (wrap/_wrap_macos/_wrap_linux), re-scoped docstrings, WR-2 `_scrub_env` docstring note, removed unused `_bwrap_warning_emitted` global
- `tests/test_sandbox.py` - `TestWrapConfineFailLoud` (5 new tests), rewrote 3 obsolete `TestWrapLinux` tests that asserted the retired observe-fallback behavior
- `flowstate/gsd_vendor.py` - WR-2 comment at both `wrap()` call sites (npm install + node parity check)

## Decisions Made
- D-01/SBX-06 scope: the raise applies ONLY to "no confinement at all achievable" — unsupported platform, bwrap absent/non-functional, sandbox-exec missing. Partial capability (bwrap present, landlock absent) is still real confinement and does not raise. `observe` is completely untouched.
- Reused `check_bwrap_available()`'s functional smoke test (not a bare presence check) for the Linux raise decision, per the plan's explicit preference (AppArmor can block a present `bwrap` binary).
- `SandboxUnavailableError(RuntimeError)` chosen over reusing `OSError` (the strongest same-file precedent) — a single-purpose exception name makes call sites more self-documenting; no hierarchy introduced.
- D-04 (WR-2): documented, not fixed. The `_TOKEN` suffix denylist entry is deliberately NOT exempted for tool-auth vars like `NPM_TOKEN` — widening it would weaken the scrub's core guarantee for every `observe` caller.

## Deviations from Plan

None - plan executed exactly as written. The plan's own Task 2 scope ("rewrite/extend test_sandbox.py") absorbed the 3 pre-existing `TestWrapLinux` tests that directly exercised `_wrap_linux`'s retired print-and-degrade-to-observe behavior (`test_wrap_linux_falls_back_to_observe`, `test_wrap_linux_observe_fallback_never_raises`, `test_wrap_linux_observe_fallback_emits_one_time_warning`) — these weren't explicitly named in the plan's Task 2 action text (which named `test_unsupported_platform_confine_returns_scrubbed` specifically) but were clearly within its stated mandate ("rewrite/extend test_sandbox.py for the fail-loud contract") since they tested the exact code path Task 1 removed. Rewrote 2 into raise-assertions and dropped the third (which tested a stderr warning that no longer exists once the print statement was removed).

## Issues Encountered

**Worktree isolation recovery (process note, not a plan deviation):** early in this session, several Read/Edit tool calls used an absolute path that resolved to the main repo checkout (`/Users/jhogan/frameworx/...`) instead of this session's worktree, and one `git commit` (cwd-drift) landed a commit on `main` in the main repo. This was caught before further work proceeded: the errant commit was safely undone with `git revert` (non-destructive; `git reset --hard` on the protected `main` branch was correctly blocked by the environment's safety classifier), and all subsequent work was redone from scratch using explicit worktree-rooted absolute paths with a `git rev-parse --show-toplevel` check before every Edit/commit. No user-visible work was lost; `main` in the primary checkout is unaffected (a revert-of-revert-free clean state).

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- SBX-06 is now code-complete: `confine` fails loud on every no-confinement-achievable path; `observe` and partial-capability degrade are regression-guarded by tests.
- Ready for 25-02 (SBX-05 E2E confine wiring: bridge.py live spawn + WR-09 temp-profile cleanup) and the WR-03 Linux re-probe — this plan did not touch `bridge.py` or the live spawn path, only the `wrap()` seam's fail-loud contract.
- `.planning/phases/25-confinement-verification/deferred-items.md` records one out-of-scope, pre-existing full-suite failure (`test_installer_gsd.py::test_gsd_sdk_full_parity_query` — missing untracked `node_modules` in this fresh worktree checkout); not caused by this plan, not fixed here.

## Known Stubs

None.

---
*Phase: 25-confinement-verification*
*Completed: 2026-07-12*

## Self-Check: PASSED
