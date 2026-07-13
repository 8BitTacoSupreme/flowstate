---
phase: 23-linux-parity-core-seam
plan: 03
subsystem: infra
tags: [ctypes, landlock, bwrap, sandbox, linux, syscalls, security]

# Dependency graph
requires:
  - phase: 23-01
    provides: "wrap() seam, observe-tier env-scrub, platform dispatch stubs"
  - phase: 23-02
    provides: "build_macos_profile, _wrap_macos, build_linux_bwrap_args (pure builders)"
provides:
  - "_apply_landlock/_landlock_available — pure-ctypes Landlock LSM helper (syscalls 444/445/446)"
  - "check_bwrap_available — functional bwrap smoke test (not presence-only)"
  - "_wrap_linux — D-03 two-rung degradation ladder (bwrap+landlock -> bwrap-only -> observe)"
  - "python -m flowstate.sandbox --apply-landlock CLI shim (argv shape only, not yet spawned)"
affects: ["24-subprocess-wiring", "25-confine-production", "23-04-linux-spike"]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Linux-only ctypes syscall body isolated behind a sys.platform guard + # pragma: no cover, mirroring flowstate/embeddings.py's never-raise degradation shape"
    - "Functional smoke test over presence check for external sandbox binaries (bwrap --ro-bind / / -- /bin/true, not shutil.which alone)"
    - "Degradation ladder returns a usable (argv, env) tuple at every rung; never raises"

key-files:
  created: []
  modified:
    - flowstate/sandbox.py
    - tests/test_sandbox.py

key-decisions:
  - "Implemented exactly D-03's two rungs (bwrap+landlock -> bwrap-only -> observe); the invented Landlock-only rung (bwrap absent, landlock present) is explicitly REJECTED and recorded as a documented future refinement, not silently added — resolves RESEARCH Open Question #1."
  - "Landlock applied via a self-invoking python -m flowstate.sandbox --apply-landlock shim placed after bwrap's `--` separator; Phase 23 builds/golden-tests the argv SHAPE only — the live spawn/preexec wiring is deferred to Phase 25."
  - "check_bwrap_available is a functional smoke test (real bwrap invocation, exit-code check), not shutil.which alone — Ubuntu 24.04+ AppArmor userns caveat (T-23-08)."

patterns-established:
  - "TDD RED/GREEN split across three commits for the tdd=true task: stub-with-NotImplementedError + failing tests (RED), then real implementation (GREEN)."

requirements-completed: [SBX-02]

# Metrics
duration: 25min
completed: 2026-07-12
---

# Phase 23 Plan 03: Landlock ctypes helper + bwrap degradation ladder Summary

**Pure-ctypes Landlock LSM ruleset applier (syscalls 444/445/446), a functional (not presence-only) bwrap smoke test, and `_wrap_linux`'s D-03 two-rung degradation ladder — completing the Linux confinement build path for SBX-02.**

## Performance

- **Duration:** ~25 min
- **Completed:** 2026-07-12T17:16:59Z
- **Tasks:** 2 completed (Task 2 is `tdd="true"`, executed as RED then GREEN)
- **Files modified:** 2 (`flowstate/sandbox.py`, `tests/test_sandbox.py`)

## Accomplishments

- `_apply_landlock`/`_landlock_available`: a pure-stdlib `ctypes` Landlock LSM helper applying a path-beneath ruleset (syscalls 444/445/446), import-guarded on `sys.platform`, never raising off-Linux. `PR_SET_NO_NEW_PRIVS` (`prctl(38, ...)`) is called before `landlock_restrict_self` per Pitfall 5; the 16-byte-padded `struct.pack("QiI", ...)` shape is used per Pitfall 4. A locked comment forbids replacing this with `py-landlock`/`landlock` (PyPI).
- `check_bwrap_available`: replaced the presence-only stub with a functional smoke test (`bwrap --ro-bind / / -- /bin/true`, exit-code check), catching `OSError`/`TimeoutExpired` and never raising — addresses the Ubuntu 24.04+ AppArmor userns caveat (T-23-08).
- `_wrap_linux`: implements exactly D-03's two-rung ladder (RUNG 1 bwrap+landlock, RUNG 2 bwrap-only, RUNG 3 observe-fallback with a one-time stderr warning). The invented Landlock-only rung is explicitly rejected in a code comment, resolving RESEARCH Open Question #1.
- A minimal `python -m flowstate.sandbox --apply-landlock <root> -- <cmd...>` argparse shim was added as the RUNG-1 target — it builds the correct argv shape; the actual spawn/exec wiring is deferred to Phase 25 per the plan's scope boundary.
- 19 new tests added (landlock availability/no-op, `_find_bwrap` locator, `check_bwrap_available` smoke-test shape, and the three ladder rungs + never-raise guarantees).

## Task Commits

Task 2 is `tdd="true"` and produced a RED then GREEN commit as required by the TDD execution flow.

1. **Task 1: Landlock ctypes helper + kernel/ABI availability probe** - `44d2fee` (feat)
2. **Task 2 (RED): failing tests for bwrap smoke test + two-rung ladder** - `42a917b` (test)
3. **Task 2 (GREEN): implement bwrap functional smoke test + two-rung ladder** - `6aa0aa2` (feat)

**Plan metadata:** committed separately below.

## Files Created/Modified

- `flowstate/sandbox.py` - Added `_LANDLOCK_*` constants/syscall numbers, `_landlock_available`, `_apply_landlock`/`_apply_landlock_syscalls`, `_find_bwrap`, real `check_bwrap_available`, `_bwrap_warning_emitted` + real `_wrap_linux` two-rung ladder, and the `python -m flowstate.sandbox --apply-landlock` argparse shim.
- `tests/test_sandbox.py` - Added `TestLandlockAvailable`, `TestApplyLandlock`, `TestFindBwrap`, `TestCheckBwrapAvailable`, `TestWrapLinux` (19 new tests total).

## Decisions Made

- **D-03 two-rung ladder, not three:** RESEARCH's Open Question #1 flagged that `agent-sandbox-demos` documents a third "Landlock-only" rung (bwrap absent, landlock present). Per D-03's literal two-rung wording, this plan implements exactly two rungs and records the Landlock-only option as a documented future refinement in a code comment — bwrap-absent always collapses straight to observe (RUNG 3), never to a bare-landlock rung.
- **Argv-shape-only for the landlock shim:** the RUNG-1 target is `[sys.executable, "-m", "flowstate.sandbox", "--apply-landlock", str(project_root), "--", *cmd]`. This builds and golden-tests the correct argv shape; nothing in this plan calls `subprocess.run` (D-04) — the live spawn/preexec wiring that actually executes the shim is Phase 25's job.
- **Functional bwrap smoke test:** `check_bwrap_available` runs a real `bwrap --ro-bind / / -- /bin/true` invocation rather than trusting `shutil.which`, per RESEARCH Pitfall 3 (Ubuntu 24.04+ AppArmor can leave `bwrap` on PATH but non-functional).

## Deviations from Plan

None - plan executed exactly as written, including the TDD RED/GREEN gate sequence for Task 2.

## Issues Encountered

- One test suite flake unrelated to this plan's changes: `tests/test_verdict.py::test_real_mode_no_paired_data_fails_loud` failed once in a full-suite run alongside 1287 passing tests, then passed both in isolation and in a repeat full-suite run (1288 passed, 1 skipped). This is a pre-existing test-isolation issue in `test_verdict.py`, out of scope per the deviation rules' scope boundary (not caused by `flowstate/sandbox.py` or `tests/test_sandbox.py` changes) — not fixed, not logged to `deferred-items.md` since it self-resolved on rerun and no `flowstate/sandbox.py` or `tests/test_sandbox.py` files were involved.

## TDD Gate Compliance

Task 2 (`tdd="true"`) followed the full RED -> GREEN gate sequence:
- RED: `42a917b` — `_find_bwrap`/`check_bwrap_available`/`_wrap_linux` stubbed to raise `NotImplementedError`; 15 new tests added and confirmed failing before any implementation.
- GREEN: `6aa0aa2` — real implementation added; all 15 previously-failing tests pass, plus the full `tests/test_sandbox.py` suite (54 tests) and the full repo suite (1288 tests, 91.05% coverage) pass.
- No fail-fast violation: no test passed unexpectedly during RED.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- The Linux confine path (`check_bwrap_available`, `_apply_landlock`, `_wrap_linux`) is fully built and unit-tested; nothing is wired into a live caller yet (Phase 24/25 scope, as designed).
- The Landlock syscall body's actual allow/deny behavior on real Linux hardware is unverified on this Darwin dev machine (syscall body carries `# pragma: no cover`) — behavioral verification is plan 23-04's SBX-01 spike, not this plan.
- Ready for plan 23-04 (the Linux spike) and eventually Phase 24's call-site wiring.

---
*Phase: 23-linux-parity-core-seam*
*Completed: 2026-07-12*

## Self-Check: PASSED

All claimed files and commit hashes verified present on disk / in git history.
