---
phase: 25-confinement-verification
plan: 02
subsystem: infra
tags: [sandbox, subprocess, confine, macos, sandbox-exec, tempfile]
status: complete

# Dependency graph
requires:
  - phase: 24-thread-the-seam-config
    provides: "wrap(cmd, surface, project_root, env, tier=...) live at bridge.py:309, ProjectPreferences.sandbox threaded"
provides:
  - "finally-guarded unlink(missing_ok=True) of the temp macOS .sb SBPL profile after every ClaudeBridge.run() confine-tier call"
  - "test coverage proving the cleanup fires on success, subprocess.TimeoutExpired, and FileNotFoundError, and is inert for observe-tier calls"
affects: [25-confinement-verification]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "try/finally temp-artifact cleanup nested around an existing try/except (bench/replicate.py:_run_trial analog), not replacing the existing except handlers"

key-files:
  created: []
  modified:
    - flowstate/bridge.py
    - tests/test_bridge.py

key-decisions:
  - "Detect the confine+darwin argv shape via `self.config.sandbox == 'confine' and sys.platform == 'darwin' and len(cmd) > 2`, capturing cmd[2] as profile_path BEFORE subprocess.run, rather than inspecting cmd[0] against the located sandbox-exec binary path"
  - "No sandbox.run() spawn helper introduced — cleanup wired at the existing bridge.py call site per the locked (argv, env) tuple contract (D-04)"

patterns-established:
  - "WR-09/SBX-05 cross-reference comments at both the capture site and the finally block"

requirements-completed: [SBX-05]

# Metrics
duration: ~12min
completed: 2026-07-12
---

# Phase 25 Plan 02: WR-09 Temp-Profile Cleanup Summary

**try/finally `unlink(missing_ok=True)` around `ClaudeBridge.run()`'s confined `subprocess.run` closes the WR-09 `.sb` temp-file leak on every exit path.**

## Performance

- **Duration:** ~12 min
- **Started:** 2026-07-12T23:25:00Z
- **Completed:** 2026-07-12T23:29:53Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- `ClaudeBridge.run()` now captures the macOS confine-tier temp `.sb` profile path (`cmd[2]`) immediately after `wrap()` returns, only when the argv is the `confine`+`darwin` `sandbox-exec -f <path>` shape
- The existing `subprocess.run` try/except (`TimeoutExpired`, `FileNotFoundError`) is now nested inside a `try/finally` that unlinks the captured profile with `missing_ok=True` on every exit path — success, timeout, or file-not-found
- Four new tests prove: success-path cleanup, timeout-path cleanup, FileNotFoundError-path cleanup, and observe-tier inertness (no unlink attempted, no error)

## Task Commits

Each task was committed atomically:

1. **Task 1: try/finally temp-profile unlink around the confined subprocess.run (WR-09)** - `73a23d9` (feat)
2. **Task 2: Cleanup test — no .sb leak on success and error paths** - `5c60549` (test)

**Plan metadata:** (this SUMMARY commit)

## Files Created/Modified
- `flowstate/bridge.py` - Added `import sys`; capture `profile_path` right after `wrap()` returns (confine+darwin+len(cmd)>2 guard); wrapped the existing `try/except subprocess.TimeoutExpired/FileNotFoundError` block in an outer `try/finally` that does `Path(profile_path).unlink(missing_ok=True)` when `profile_path is not None`
- `tests/test_bridge.py` - Added `TestConfineTempProfileCleanup`: forces the confine→macOS dispatch via `monkeypatch.setattr` on `flowstate.bridge.sys.platform` and `flowstate.sandbox.sys.platform` (so the suite passes on any host OS), stubs `subprocess.run` to avoid spawning real `sandbox-exec`/`claude`, and asserts the real on-disk `.sb` file `_wrap_macos` creates is gone after `bridge.run()` returns — on the success path and on both error paths — plus a regression test that observe-tier `run()` is unaffected

## Decisions Made
- Used the tier+platform check (`self.config.sandbox == "confine" and sys.platform == "darwin"`) rather than matching `cmd[0]` against the located `sandbox-exec` binary path — simpler, matches the PATTERNS.md guidance, and avoids a second binary-location lookup at the call site
- Did not introduce a `sandbox.run()` spawn helper; cleanup lives entirely at the `bridge.py:309` call site, preserving the Phase 23 `(argv, env)` tuple contract (D-04, locked)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None. The `uv.lock` file was incidentally touched by `uv sync --extra dev` while setting up the test environment (installing dev dependencies not previously synced in this worktree); reverted via `git checkout -- uv.lock` before committing since it was unrelated to this plan's scope and out of bounds per CLAUDE.md's "no new runtime dependencies" constraint (dev-only tooling, not a real dependency add, but still not part of this plan's file scope).

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- WR-09 is closed at the primary confine call site (`bridge.py`). The `distiller.py:96` confine call site (also wrapping `wrap(..., tier=...)`) was noted in CONTEXT.md as a possible secondary site but is out of this plan's declared `files_modified` scope (`flowstate/bridge.py`, `tests/test_bridge.py` only) — if `distiller.py` is ever run at `confine` tier, it would leak the same way and should be checked in a later plan/phase if that surface goes production-confine.
- Remaining Phase 25 work (SBX-05 E2E denial proof, SBX-06 fail-loud, WR-03 Linux re-probe) is scoped to other plans in this phase's wave structure and is unaffected by this plan.

---
*Phase: 25-confinement-verification*
*Completed: 2026-07-12*
