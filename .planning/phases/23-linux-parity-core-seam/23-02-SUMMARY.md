---
phase: 23-linux-parity-core-seam
plan: 02
subsystem: infra
tags: [sandbox, seatbelt, sbpl, bwrap, macos, linux, security]

# Dependency graph
requires:
  - phase: 23-01
    provides: "flowstate/sandbox.py's wrap() seam, observe tier, env-scrub denylist, and confine-tier contract stubs (build_macos_profile, build_linux_bwrap_args, _wrap_macos, _wrap_linux, check_bwrap_available)"
provides:
  - "build_macos_profile(project_root) -> str — byte-exact, golden-tested macOS SBPL allow-default + selective-deny profile"
  - "_find_sandbox_exec() -> str — FLOWSTATE_SANDBOX_EXEC_BIN > which > /usr/bin/sandbox-exec locator"
  - "_wrap_macos(cmd, project_root, env) -> (argv, env) — writes profile to a temp .sb file, prefixes argv with sandbox-exec -f <path>"
  - "build_linux_bwrap_args(project_root) -> list[str] — deterministic bwrap mount-namespace arg list (args-only convention, no binary/--/cmd)"
affects: [24-wire-the-seam, 25-confine-production]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Pure, I/O-free profile/argv builders (RESEARCH Pattern 1) — golden-tested via exact string/list equality, not substring membership"
    - "FLOWSTATE_<TOOL>_BIN > shutil.which > fallback-candidate locator (mirrors pack.py:_find_repomix / gsd_vendor.py's _find_npm/_find_node)"

key-files:
  created: []
  modified:
    - flowstate/sandbox.py
    - tests/test_sandbox.py

key-decisions:
  - "Split the two-task plan into two atomic commits by temporarily stubbing build_linux_bwrap_args back to NotImplementedError for the Task 1 commit, then restoring it for Task 2 — both functions were implemented in the same editing pass but committed separately to preserve per-task atomicity"
  - "build_linux_bwrap_args returns ARGS ONLY (no bwrap binary, no -- separator, no target cmd) per the plan's documented convention; _wrap_linux (23-03) owns final assembly"

patterns-established:
  - "Golden test classes assert exact string/list equality against a literal built from the same project_root/Path.home(), not just substring containment (TestBuildMacosProfile, TestBuildLinuxBwrapArgs)"

requirements-completed: [SBX-02]

# Metrics
duration: 9min
completed: 2026-07-12
---

# Phase 23 Plan 02: macOS SBPL Profile Builder + Linux bwrap Args Summary

**Spike-proven macOS Seatbelt profile builder (allow-default + selective-deny) and deterministic Linux bwrap mount-namespace argv builder, both pure/I-O-free and golden-tested; neither wired to a live caller yet.**

## Performance

- **Duration:** ~9 min
- **Started:** 2026-07-12T12:49:57-04:00
- **Completed:** 2026-07-12T12:58:15-04:00
- **Tasks:** 2 completed
- **Files modified:** 2

## Accomplishments
- `build_macos_profile(project_root)` emits the exact spike-proven SBPL shape byte-for-byte: `(allow default)` baseline, selective `(deny file-write*)` re-allowing `project_root`/`/private/tmp`/`/private/var/folders`/`/dev`, then `(deny file-read* (subpath ~/.ssh))`
- `_wrap_macos()` writes the profile to a temp `.sb` file and prefixes argv with `sandbox-exec -f <path>`, passing env through unchanged — matching `_find_sandbox_exec()`'s locator to the codebase's `FLOWSTATE_<TOOL>_BIN > which > fallback` convention (`pack.py:_find_repomix`)
- `build_linux_bwrap_args(project_root)` returns the deterministic bwrap mount-namespace flag sequence (project writable, `~/.ssh` shadowed via `--tmpfs`, PID/UTS/IPC unshared, `--die-with-parent`), documented as an args-only builder that `_wrap_linux` (23-03) will assemble into a full command
- Both builders are golden-tested (exact string/list equality, not substring) and run cleanly on this darwin dev machine with zero subprocess/ctypes/file I/O inside the builder bodies

## Task Commits

Each task was committed atomically:

1. **Task 1: macOS SBPL builder + _wrap_macos confine wiring** - `8290553` (feat)
2. **Task 2: Linux bwrap mount-namespace argv builder (pure)** - `78ddedd` (feat)

**Plan metadata:** (this commit, following SUMMARY creation)

_Note: Task 1 and Task 2 were implemented together in the same editing pass, then split into two atomic commits by temporarily reverting `build_linux_bwrap_args` to its `NotImplementedError` stub for the Task 1 commit, then restoring the implementation for the Task 2 commit — see Deviations._

## Files Created/Modified
- `flowstate/sandbox.py` - Implements `build_macos_profile`, `_find_sandbox_exec`, `_wrap_macos`, `build_linux_bwrap_args`; `check_bwrap_available` and `_wrap_linux` remain contract stubs for plan 23-03
- `tests/test_sandbox.py` - Adds `TestBuildMacosProfile`, `TestFindSandboxExec`, `TestWrapMacos`, `TestBuildLinuxBwrapArgs` classes (37 new/total test functions in the file, all passing)

## Decisions Made
- Golden tests assert byte-exact string equality (macOS) and exact list equality (Linux args) against literals built from the same `project_root`/`Path.home()` inputs — locks the shape so a future edit that weakens the profile fails the test (T-23-05 mitigation)
- `_wrap_macos` uses `tempfile.NamedTemporaryFile(delete=False)` since `sandbox-exec` requires a file path, not stdin — matches the RESEARCH Standard Stack note and sandflox's own `WriteSBPL()` behavior
- `build_linux_bwrap_args` deliberately excludes the `bwrap` binary path and `--`/cmd assembly, documented in its docstring as the convention `_wrap_linux` (23-03) will follow

## Deviations from Plan

None functionally — plan executed exactly as specified. One process deviation for commit hygiene:

**Commit-splitting maneuver (not a Rule 1-4 deviation, a process choice):** Both tasks' code was written in a single editing pass since they share the same file and are tightly coupled. To honor the per-task atomic-commit requirement, `build_linux_bwrap_args` was temporarily reverted to its `NotImplementedError` stub (and its `TestBuildLinuxBwrapArgs` test class + import temporarily removed) before the Task 1 commit, then restored immediately after for the Task 2 commit. Both intermediate and final states were verified with `pytest`/`ruff` before each commit.

**Total deviations:** 0 auto-fixed
**Impact on plan:** None — plan executed exactly as written, both tasks' acceptance criteria verified independently.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- `build_macos_profile`, `_wrap_macos`, and `build_linux_bwrap_args` are implemented, golden-tested, and ready for plan 23-03 to build `_wrap_linux` (landlock ctypes application + `bwrap` binary dispatch) and `check_bwrap_available` on top of them
- Neither builder is wired into any of the 8 subprocess call sites yet — that remains Phase 24 (SBX-03) scope, matching the plan's explicit non-goal
- The `confine` tier is not shipped for real production use in this phase (Phase 25, SBX-05/06 concern) — `sandbox-exec`/`bwrap` invocation correctness has not been exercised end-to-end, only the argv/profile construction

---
*Phase: 23-linux-parity-core-seam*
*Completed: 2026-07-12*

## Self-Check: PASSED

- FOUND: flowstate/sandbox.py
- FOUND: tests/test_sandbox.py
- FOUND: .planning/phases/23-linux-parity-core-seam/23-02-SUMMARY.md
- FOUND commit: 8290553
- FOUND commit: 78ddedd
