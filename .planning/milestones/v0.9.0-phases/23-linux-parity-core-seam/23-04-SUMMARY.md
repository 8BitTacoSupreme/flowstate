---
phase: 23-linux-parity-core-seam
plan: 04
subsystem: infra
tags: [bwrap, landlock, docker, sandbox, linux, spike, auth]

# Dependency graph
requires:
  - phase: 23-01
    provides: "wrap() seam, observe-tier env-scrub, platform dispatch stubs"
  - phase: 23-02
    provides: "build_linux_bwrap_args (pure bwrap mount-namespace arg builder)"
  - phase: 23-03
    provides: "_apply_landlock/_landlock_available ctypes helper, D-03 two-rung degradation ladder"
provides:
  - "23-SPIKE-LINUX.md — committed SBX-01 verdict: PARITY PROVEN"
  - "Real-kernel evidence that Landlock (ABI v6) and bwrap+landlock combined confine filesystem writes (allow /tmp, deny /root; EACCES and EROFS denial shapes)"
  - "Real-kernel evidence that a confined `claude --print` under bwrap mount-namespace confinement preserves auth and API reachability (token-path, exit 0, real model output)"
affects: ["24-thread-seam-config", "25-confine-production"]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Docker ubuntu:24.04 --rm as a throwaway Linux spike environment (no project dependency added)"
    - "--env-file for credential injection into a container, never as a CLI arg or logged value"

key-files:
  created:
    - .planning/phases/23-linux-parity-core-seam/23-SPIKE-LINUX.md
  modified: []

key-decisions:
  - "VERDICT: PARITY PROVEN — Linux confine ships in Phase 25 rather than degrading to observe-only. Both the filesystem-confinement mechanism (Task 1) and claude auth-preservation under the same bwrap mount-namespace profile (Task 2) were demonstrated on a real kernel (6.12.76-linuxkit, aarch64, Landlock ABI v6)."
  - "npm-fallback install path used for the claude CLI inside the ephemeral container (native install.sh succeeded but the binary wasn't resolved within the probe script's PATH/find scope) — not a spike failure, documented in the artifact for completeness."
  - "Auth probe used the OAuth token-path (CLAUDE_CODE_OAUTH_TOKEN via --env-file, human-minted via `claude setup-token`), not the file-path (~/.claude/.credentials.json), per RESEARCH Open Question #3. bwrap preserves inherited env vars (no --clearenv), which is how the token reached the confined process."

requirements-completed: [SBX-01]

# Metrics
duration: ~25min (Task 2 probe + Task 3 write-up; Task 1 mechanism spike ran in a prior session)
completed: 2026-07-12
---

# Phase 23 Plan 04: Linux bwrap+landlock Spike Summary

**SBX-01 retired: Docker-based Linux spike proves bwrap+landlock confines filesystem writes (EACCES/EROFS) and a confined `claude --print` under the same bwrap profile authenticates and reaches the API — PARITY PROVEN, Linux confine ships in Phase 25.**

## Performance

- **Duration:** ~25 min (this continuation session: Task 2 auth probe + Task 3 artifact/commit)
- **Completed:** 2026-07-12
- **Tasks:** 3 (Task 1 mechanism spike — done in prior session; Task 2 auth-preservation checkpoint — resolved this session; Task 3 verdict artifact — written and committed this session)
- **Files modified:** 2 (23-SPIKE-LINUX.md created, this SUMMARY created)

## Accomplishments
- Confirmed Landlock (ABI v6) and bwrap+landlock combined confine filesystem writes on a real Linux kernel (6.12.76-linuxkit, aarch64) inside Docker — write-allowed `/tmp`, write-denied `/root`, both EACCES (pure Landlock) and EROFS (bwrap `--ro-bind`) denial shapes captured via broad `OSError` catch.
- Ran a confined `claude --print` under the bwrap mount-namespace profile with a human-minted OAuth token injected only via `docker run --env-file`; got exit code 0 and real model output (`4`) — auth preserved under confinement.
- Wrote and committed `.planning/phases/23-linux-parity-core-seam/23-SPIKE-LINUX.md` with all six required sections (Environment, Mechanism result, Auth-preservation result, Degradation ladder observed, VERDICT, Consequence for phases 24-25) and an unambiguous **PARITY PROVEN** verdict.
- Verified no OAuth token value leaked into the committed artifact, git history, or any logged output; deleted the scratchpad credential file after use.

## Task Commits

Each task was committed atomically:

1. **Task 1: Landlock + bwrap mechanism spike** — no repo commit (scratchpad-only evidence file, consumed by Task 3; completed in a prior session, evidence at `landlock_spike_output.txt`)
2. **Task 2: Auth-preservation checkpoint** — human-action checkpoint resolved this session (credential provided, confined probe run); no separate commit (probe output captured to scratchpad, consumed by Task 3)
3. **Task 3: Write and commit 23-SPIKE-LINUX.md** — `8e94b44` (docs)

**Plan metadata:** this SUMMARY + STATE/ROADMAP/REQUIREMENTS updates (see final metadata commit)

## Files Created/Modified
- `.planning/phases/23-linux-parity-core-seam/23-SPIKE-LINUX.md` - Committed SBX-01 verdict artifact (PARITY PROVEN)

## Decisions Made
- PARITY PROVEN, not PARITY GAP: both the mechanism and the auth halves passed on the first real-kernel attempt, so no bwrap-only fallback variant was needed to isolate an auth-vs-filesystem failure — see artifact Section 3 for scope notes on what was and wasn't jointly exercised (bwrap mount-namespace confinement + auth, proven together; landlock-wrapped-into-the-claude-process-launch itself is deferred integration work for Phase 24/25, not a new unknown).

## Deviations from Plan

None - plan executed exactly as written. The npm-fallback install path (noted above) was already anticipated in the orchestrator's Task 2 recipe as a fallback option, not an improvised deviation.

## Issues Encountered
- The native `curl -fsSL https://claude.ai/install.sh | bash` installer succeeded (exit 0) inside the container but the resulting binary at `~/.local/bin/claude` wasn't found by `command -v` / a depth-limited `find` in the ephemeral shell (PATH not refreshed). Resolved by falling back to `npm install -g @anthropic-ai/claude-code` per the orchestrator's documented fallback — the resulting binary (`/usr/local/bin/claude`) ran the confined probe successfully.

## User Setup Required
None - the OAuth token credential was a one-time checkpoint input, already consumed and deleted; no ongoing external service configuration required for this plan.

## Next Phase Readiness
- SBX-01 is fully retired with a committed, unambiguous verdict. Phase 24 (thread the seam + config) can wire `flowstate/sandbox.py`'s `wrap()` seam through agent-directed subprocess sites and expose the `ProjectPreferences.sandbox` config field with Linux and macOS both supporting the `confine` tier (not just `observe`) from the start.
- Phase 25 (Linux confine profile ships) has both the mount-namespace confinement (23-02's `build_linux_bwrap_args`) and the Landlock ctypes helper (23-03's `_apply_landlock`) individually proven on a real kernel; the remaining integration work is composing them into a single process launch, not discovering whether they're compatible.
- No blockers.

---
*Phase: 23-linux-parity-core-seam*
*Completed: 2026-07-12*
