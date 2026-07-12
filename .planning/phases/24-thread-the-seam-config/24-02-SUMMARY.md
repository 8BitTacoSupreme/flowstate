---
phase: 24-thread-the-seam-config
plan: 02
subsystem: infra
tags: [sandbox, subprocess, security, repomix, npm, gsd-vendor, tool-adapter]

# Dependency graph
requires:
  - phase: 24-thread-the-seam-config (plan 01)
    provides: ProjectPreferences.sandbox field, bridge.py + distiller.py "llm" sites wrapped, _make_bridge threading
  - phase: 23-linux-parity-core-seam
    provides: flowstate.sandbox.wrap(cmd, surface, project_root, env, tier=) seam contract
provides:
  - "ToolAdapter.run_cmd wrapped at surface \"tool\" with a threaded sandbox level"
  - "pack.py's repomix subprocess wrapped at surface \"tool\", threaded from CLI-loaded state"
  - "gsd_vendor.py's npm install + node parity subprocesses wrapped at surface \"tool\" (default observe, not project-scoped)"
  - "discipline.py's bare git/pytest exclusion recorded as a visible SBX-03/D-01 comment"
  - "Full test suite (1315 tests, 91.37% coverage) proving default observe ships without regression"
affects: [25-confine-tier-production-profiles]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "wrap(cmd, \"tool\", project_root, env, tier=level) immediately before every non-llm subprocess.run call that touches agent-directed or remote content"
    - "Sites that are not project-scoped (gsd_vendor.refresh) wrap at the hardcoded default observe tier with Path.cwd() as the project_root placeholder, rather than adding a sandbox param nobody can thread"
    - "Deliberate bare-exclusion sites get a sourced SBX-03/D-<n> comment at the code site, not a silent omission"

key-files:
  created: []
  modified:
    - flowstate/tools/base.py
    - flowstate/orchestrator.py
    - flowstate/pack.py
    - flowstate/gsd_vendor.py
    - flowstate/cli.py
    - flowstate/discipline.py
    - tests/test_tools_extended.py
    - tests/test_pack.py
    - tests/test_gsd_vendor.py
    - tests/test_cli.py

key-decisions:
  - "gsd_vendor.refresh() wraps both subprocess sites at the hardcoded default observe tier (no sandbox param added) because its only caller (gsd_version --refresh) is not project-scoped and never calls resolve_root()"
  - "context_prefix.py:607's auto-pack caller is intentionally left at run_pack's default (observe) — env-scrub still fires, no sandbox threading added there per plan scope"
  - "discipline.py's four git/pytest subprocess.run calls stay bare with a sourced SBX-03/D-01 comment at both physical locations, per the phase's locked D-01 decision"

patterns-established:
  - "Pattern: subprocess sites that receive agent-directed/remote content route through wrap(\"tool\", ...) immediately before subprocess.run, mirroring bridge.py's \"llm\" surface pattern from plan 24-01"

requirements-completed: [SBX-03]

# Metrics
duration: ~25min
completed: 2026-07-12
---

# Phase 24 Plan 02: Thread the Seam — Tool Sites Summary

**Wrapped the four remaining SBX-03 "tool" subprocess sites (adapter run_cmd, repomix, npm install, node parity) through `wrap()` with explicit scrubbed envs, and recorded discipline.py's bare git/pytest sites as a deliberate, sourced exclusion.**

## Performance

- **Duration:** ~25 min
- **Completed:** 2026-07-12T21:51:57Z
- **Tasks:** 3 completed
- **Files modified:** 10 (6 source, 4 test)

## Accomplishments
- `ToolAdapter.run_cmd` now threads `wrap(cmd, "tool", self.root, env, tier=self.sandbox)` before every subprocess.run call, and the orchestrator constructs `ResearchAdapter`/`StrategyAdapter` with `sandbox=state.preferences.sandbox`
- `run_pack()` gained a `sandbox: str = "observe"` parameter wired through the repomix `wrap("tool", ...)` call; both CLI callers (`kickoff`, `pack`) pass `sandbox=state.preferences.sandbox` from the already-loaded `state` (no extra `load_state` call)
- `gsd_vendor.refresh()` wraps both its npm install and node parity subprocess sites at the default observe tier — deliberately with no `sandbox` param, since `refresh` is invoked from `gsd_version --refresh`, which has no project root
- `discipline.py`'s four git/pytest subprocess.run calls (`_read_git_state` x3, `_run_project_tests` x1) are now visibly marked with SBX-03/D-01 exclusion comments at both physical locations — comment-only diff, zero executable-line change
- Full suite run as the D-04 no-regression proof: 1315 passed, 1 skipped, 91.37% coverage — every previously-wrapped subprocess (claude/repomix/npm/node/adapter) plus the bare git/pytest reads still function under default observe

## Task Commits

Each task was committed atomically:

1. **Task 1: Wrap ToolAdapter.run_cmd at surface "tool" + thread sandbox from the orchestrator** - `6891540` (feat)
2. **Task 2: Wrap pack.py repomix + gsd_vendor.py npm/node sites at surface "tool"** - `5b69f52` (feat)
3. **Task 3: Mark the discipline.py bare-exclusion (D-01) + full-suite no-regression proof (D-04)** - `7caf147` (docs)

_TDD tasks 1 and 2 each carry a single commit (test additions were folded into the same commit as the implementation, verified green before committing — no separate RED-phase commit was warranted since these are additive wraps to existing tested code paths, not new user-facing behavior)._

## Files Created/Modified
- `flowstate/tools/base.py` - `ToolAdapter.__init__` gains `sandbox: str = "observe"`; `run_cmd` routes through `wrap("tool", ...)` with an explicit scrubbed env before `subprocess.run`
- `flowstate/orchestrator.py` - `ResearchAdapter`/`StrategyAdapter` constructed with `sandbox=state.preferences.sandbox`
- `flowstate/pack.py` - `run_pack(root, *, compress=False, sandbox="observe")`; repomix `subprocess.run` gets `env=` from `wrap("tool", ...)`
- `flowstate/gsd_vendor.py` - both `refresh()` subprocess sites (npm install, node parity) wrapped at the default observe tier with `Path.cwd()` as `project_root`
- `flowstate/cli.py` - `kickoff` and `pack` commands pass `sandbox=state.preferences.sandbox` to `run_pack`; `gsd_version` untouched
- `flowstate/discipline.py` - two comment-only additions marking the SBX-03/D-01 bare-exclusion at `_read_git_state` and `_run_project_tests`
- `tests/test_tools_extended.py` - env-scrub assertion test for `run_cmd`
- `tests/test_pack.py` - env-scrub assertion test for the repomix call
- `tests/test_gsd_vendor.py` - env-scrub assertion test for both npm and node parity calls
- `tests/test_cli.py` - fixed a pre-existing `fake_pack` stub signature that broke once `run_pack` gained the `sandbox` kwarg

## Decisions Made
- `gsd_vendor.refresh()` does not accept a `sandbox` parameter — it wraps both subprocess sites at the hardcoded default observe tier with `Path.cwd()` as the `project_root` placeholder (observe ignores `project_root` entirely), matching the plan's explicit instruction that refresh is not project-scoped
- Left `context_prefix.py:607`'s auto-pack caller at `run_pack`'s default (observe) rather than threading a preference through it — out of this plan's scope per the action text; env-scrub still fires there since it's the function's default

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed a pre-existing test stub broken by the new `run_pack` kwarg**
- **Found during:** Task 2 (Wrap pack.py repomix + gsd_vendor.py npm/node sites)
- **Issue:** `tests/test_cli.py::TestKickoffCommand::test_kickoff_calls_run_pack_once` defines a `fake_pack(root, *, compress=False)` stub with no `**kwargs` catch-all; once `cli.py`'s `kickoff` command started passing `sandbox=state.preferences.sandbox` to `run_pack`, the stub raised `TypeError: unexpected keyword argument 'sandbox'`
- **Fix:** Added `sandbox="observe"` to the stub's signature (mirroring the real `run_pack` default)
- **Files modified:** `tests/test_cli.py`
- **Verification:** `uv run python -m pytest tests/test_cli.py -k kickoff` passes; full suite green
- **Committed in:** `5b69f52` (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking test-signature drift)
**Impact on plan:** Necessary to keep the existing test suite green after adding the `sandbox` kwarg to `run_pack`. No scope creep — `tests/test_cli.py` was not in the plan's declared `files_modified` list but the fix is a one-line signature update directly caused by this plan's change.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- The SBX-03 site inventory is now closed: all 8 sites accounted for — 2 "llm" sites (plan 24-01), 4 "tool" sites (this plan), 4 bare git/pytest sites with a sourced exclusion comment (this plan)
- Default `observe` posture is live everywhere and proven non-regressing at 91.37% coverage across 1315 tests
- Ready for Phase 25: `confine`-tier production profiles, the E2E write-denied/`~/.ssh`-denied proof, fail-loud on missing sandbox binary, and the WR-03 production-shape confirmations remain deliberately deferred, as scoped

---
*Phase: 24-thread-the-seam-config*
*Completed: 2026-07-12*

## Self-Check: PASSED

All created/modified files verified present on disk; all 3 task commit hashes verified in git log.
