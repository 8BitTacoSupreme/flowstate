---
phase: 25-confinement-verification
plan: 03
subsystem: testing
tags: [sandbox, sandbox-exec, macos, e2e, confine, pytest, skipif]
status: complete

# Dependency graph
requires:
  - phase: 25-confinement-verification
    provides: "flowstate/sandbox.py wrap(..., tier='confine') + build_macos_profile (25-01); ClaudeBridge WR-09 temp-profile cleanup (25-02)"
provides:
  - "tests/test_sandbox_e2e_macos.py — real, non-mocked, skip-if-not-darwin E2E proof of SBX-05's macOS half"
  - "empirically-confirmed real sandbox-exec behavior: allow-write inside project_root, deny-write outside (under $HOME), deny-read of ~/.ssh (directory-level, no leaked listing/content)"
  - "claude-availability-gated proof that ClaudeBridge(sandbox='confine') preserves macOS Keychain auth and reaches the Anthropic API through a real confined sandbox-exec call"
affects: [25-confinement-verification]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "skip-if-not-darwin real-subprocess E2E test (tests/test_discipline.py's shutil.which()-is-None skipif idiom translated to a sys.platform != 'darwin' gate)"
    - "direct wrap()+subprocess.run callers own their own temp .sb profile cleanup in a finally, distinct from the bridge's WR-09 cleanup"

key-files:
  created:
    - tests/test_sandbox_e2e_macos.py
  modified: []

key-decisions:
  - "~/.ssh denial probed via `ls -la <ssh_dir>` (directory-level read) rather than reading a specific file inside it — empirically confirmed on the real dev machine that file-read* denies the directory stat/opendir itself (nonzero exit, empty stdout), which is a stronger and simpler proof than guessing at file names that may not exist on every host"
  - "Auth subcheck uses `inject_canon=False` + `max_turns=1` + a minimal 'reply with only the digit 4' prompt to bound real API cost/time, mirroring the 23-SPIKE-LINUX.md minimal-probe shape"
  - "Task 1 and Task 2 committed as separate atomic commits against the same file (task 1 adds the file with the denial-proof class; task 2 appends the auth-subcheck class) rather than one combined commit, per plan structure"

patterns-established:
  - "New test files exercising real platform mechanisms (not mocked) gate with a module-level `_not_darwin`/`_claude_missing` bool + `@pytest.mark.skipif`, never a monkeypatched dispatch — reserves the monkeypatch dispatch style (tests/test_sandbox.py, tests/test_bridge.py) for offline coverage of the same code paths"

requirements-completed: [SBX-05]

# Metrics
duration: ~15min
completed: 2026-07-12
---

# Phase 25 Plan 03: macOS Confine E2E Denial + Auth-Survival Proof Summary

**Real (non-mocked) `sandbox-exec` under the shipped `build_macos_profile` proven on the dev machine: writes inside `project_root` succeed, writes outside it (under `$HOME`) and reads of `~/.ssh` are denied, and a confined `claude --print` via the production `ClaudeBridge(sandbox="confine")` path still authenticates via Keychain and reaches the API.**

## Performance

- **Duration:** ~15 min
- **Tasks:** 2 completed
- **Files modified:** 1 (created)

## Accomplishments

- New `tests/test_sandbox_e2e_macos.py` exercises the actual shipped confine path — `flowstate.sandbox.wrap(..., tier="confine")` → real `sandbox-exec` under `build_macos_profile` — with zero mocking, skip-gated `skipif(sys.platform != "darwin")`.
- Empirically confirmed (both via a manual real-`sandbox-exec` probe and the pytest run itself, on this darwin dev machine) that the spike-proven profile shape behaves exactly as designed: allow-write inside `project_root`, deny-write to `$HOME` (escape file never created), deny-read of `~/.ssh` (nonzero exit, no directory listing leaked).
- Added a claude-availability-gated auth-survival subcheck driving the real production `ClaudeBridge(sandbox="confine")` path — proved a real confined `claude --print` call succeeds, output contains a real model response, and (implicitly, since it exercises the same code path) the 25-02 WR-09 temp-profile cleanup fires without leaking a `.sb` file.
- All 4 tests pass on this machine (`sandbox-exec` and `claude` both present); `ruff check` clean.

## Task Commits

Each task was committed atomically:

1. **Task 1: macOS confine denial E2E — allow-inside / deny-outside / deny-~/.ssh** - `86a6f5a` (test)
2. **Task 2: Auth-survival subcheck — confined claude --print succeeds (Keychain preserved)** - `25fc4de` (test)

## Files Created/Modified

- `tests/test_sandbox_e2e_macos.py` - Real, skip-if-not-darwin E2E test module: `TestMacosConfineDenialE2E` (3 tests: write-inside succeeds, write-outside-`$HOME` denied, `~/.ssh` read denied) + `TestConfinedClaudeAuthSurvives` (1 test, double-gated on darwin + claude availability: confined `claude --print` succeeds via the production `ClaudeBridge` path).

## Decisions Made

- Chose a directory-level `ls -la ~/.ssh` denial probe over a named-file `cat` probe — verified via a real manual `sandbox-exec` invocation on the dev machine before committing to the assertion shape (per the plan's "do not guess, do not weaken assertions" constraint). The profile's `(deny file-read* (subpath "~/.ssh"))` clause denies the directory stat/opendir itself, giving a robust nonzero-exit + empty-stdout signal regardless of what files (if any) exist inside `~/.ssh` on a given host.
- Bounded the auth subcheck's cost/time with `inject_canon=False`, `max_turns=1`, and a minimal one-digit-reply prompt — the call completed in ~2s total alongside the 3 denial tests.
- Kept the two tasks as separate atomic commits on the same file (task 1's write created the file; task 2's edit appended the second test class), matching the plan's per-task commit protocol even though both tasks touch one file.

## Deviations from Plan

**1. [Rule 1 - Bug] Fixed a dropped `env` in the initial draft's `_run_confined` helper**
- **Found during:** Task 1 (writing the direct `wrap()`+`subprocess.run` denial helper)
- **Issue:** First draft called `_REAL_RUN(cmd, capture_output=True, text=True, timeout=10)` without passing the `env` dict returned by `wrap()`, silently discarding the scrubbed environment `ruff` flagged (`RUF059 Unpacked variable env is never used`) — a real correctness bug, not just a lint nit, since the whole point of `wrap()` is to hand back a transformed `(cmd, env)` pair for the caller to use together.
- **Fix:** Pass `env=env` to the `subprocess.run` call.
- **Files modified:** `tests/test_sandbox_e2e_macos.py`
- **Verification:** `ruff check` clean; all 4 tests still pass.
- **Committed in:** `86a6f5a` (part of Task 1 commit — caught before the first commit, not a follow-up fix)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Caught during initial drafting, before any commit; no scope creep, no follow-up commit needed.

## Issues Encountered

- `uv sync --extra dev` (needed to get a Python 3.12 venv with `pytest`/`ruff` installed in this worktree, since the ambient `python3`/`uv run` resolved to a system Python 3.9 that fails on `flowstate/events/event.py`'s `from datetime import UTC`) produced unrelated `uv.lock` resolution churn (new transitive packages, resolution-markers). Reverted with `git checkout -- uv.lock` before staging — out of scope for this plan, not committed.
- A full-suite regression run (`pytest -q`, 1327 passed / 1 skipped / 1 failed) surfaced one pre-existing, already-documented failure (`tests/test_installer_gsd.py::test_gsd_sdk_full_parity_query` — missing `.claude/get-shit-done/node_modules` in this git worktree, unrelated to sandbox work). Already logged in `.planning/phases/25-confinement-verification/deferred-items.md` by a prior plan's executor (25-01); no new entry needed, confirmed still isolated to that one test.

## Next Phase Readiness

- SBX-05's macOS half is now E2E-proven with a real, CI-runnable, skip-gated test — no mocking, no loosened assertions.
- Ready for 25-04 (Linux confine verification / WR-03 re-probe per 25-CONTEXT.md D-02/D-03) — this plan does not touch the Linux path.
- No blockers.

---
*Phase: 25-confinement-verification*
*Completed: 2026-07-12*
