---
phase: 23-linux-parity-core-seam
verified: 2026-07-12T00:00:00Z
status: passed
score: 6/6 must-haves verified
overrides_applied: 0
---

# Phase 23: Linux Parity + Core Seam — Verification Report

**Phase Goal:** The Linux confinement unknown is retired (bwrap+landlock either preserves `claude`
auth under an allow-default profile, mirroring the passed macOS Seatbelt spike, OR the gap is
honestly documented), AND `flowstate/sandbox.py` exists with the single `wrap(cmd, surface,
project_root, env)` seam and a non-blocking `observe` tier.

**Verified:** 2026-07-12
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `flowstate/sandbox.py` exposes `wrap(cmd, surface, project_root, env)` returning an `(argv, env)` tuple | VERIFIED | `flowstate/sandbox.py:127-151` — signature matches exactly (`tier` is keyword-only, defaults to `"observe"`); return type `tuple[list[str], dict[str, str]]` |
| 2 | `wrap()` never spawns a subprocess itself (D-04) | VERIFIED | `wrap()` body (lines 142-151) contains no `subprocess.run`/`Popen`/`os.exec` call. The only `subprocess.run` in the file is inside `check_bwrap_available()` (line 377), which runs a `bwrap --ro-bind / / -- /bin/true` self-test, not `cmd`. `os.execvp` at line 499 lives inside the `if __name__ == "__main__"` guard — that only executes in the confined *child* process spawned later by the caller (Phase 25 wiring), not by `wrap()` |
| 3 | `observe` tier is env-scrub only and never blocks | VERIFIED | `wrap(..., tier="observe")` returns `cmd` untouched + `_scrub_env(env)`; `TestWrapObserve.test_argv_byte_identical_under_default_tier` and `test_observe_never_mutates_argv` confirm argv is never altered |
| 4 | `_scrub_env` is a denylist (not allowlist) with an `_AUTH_EXEMPT` carve-out that preserves `ANTHROPIC_API_KEY`/`CLAUDE_CODE_OAUTH_TOKEN`/`CLAUDE_CONFIG_DIR` | VERIFIED | `flowstate/sandbox.py:60-119` — `_AUTH_EXEMPT` frozenset checked first, before prefix/suffix/exact denylist matching; unmatched vars pass through (denylist semantics). Named regression test `test_observe_never_strips_claude_auth_vars` (test_sandbox.py:101) exists and passes, asserting all three exempt vars survive while `AWS_SECRET_ACCESS_KEY` is stripped |
| 5 | Profile builders (`build_macos_profile`, `build_linux_bwrap_args`) are golden-tested; Linux path uses bwrap+landlock with a functional `check_bwrap_available` and a two-rung degradation ladder (D-02/D-03) | VERIFIED | `TestBuildMacosProfile.test_matches_spike_proven_shape` and `TestBuildLinuxBwrapArgs.test_matches_golden_shape` assert byte-exact/list-exact equality (not substring). `check_bwrap_available` runs a real `bwrap --ro-bind / / -- /bin/true` smoke test (not `shutil.which` alone) per `TestCheckBwrapAvailable.test_smoke_test_invokes_ro_bind_bin_true`. `_wrap_linux` implements exactly RUNG1 (bwrap+landlock) → RUNG2 (bwrap-only) → RUNG3 (observe fallback with one-time stderr warning), each covered by a dedicated test in `TestWrapLinux` |
| 6 | SBX-01: Linux confinement unknown retired via a committed spike verdict (proof or honest gap) | VERIFIED | `23-SPIKE-LINUX.md` committed (`8e94b44`), contains all 6 required sections (Environment, Mechanism result, Auth-preservation result, Degradation ladder observed, VERDICT, Consequence for phases 24-25), unambiguous verdict **PARITY PROVEN**, concrete phase 24/25 consequences documented |

**Score:** 6/6 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `flowstate/sandbox.py` | `wrap()` seam + platform builders + observe tier | VERIFIED | 500 lines, substantive, no stubs remaining (all confine-path contract stubs from 23-01 were implemented in 23-02/23-03) |
| `tests/test_sandbox.py` | Unit tests for `wrap()`, golden tests for profile builders | VERIFIED | 456 lines, 54 tests, all pass in isolation (`uv run python -m pytest tests/test_sandbox.py -q` → `54 passed`) |
| `.planning/phases/23-linux-parity-core-seam/23-SPIKE-LINUX.md` | SBX-01 verdict artifact | VERIFIED | Committed at `8e94b44`, contains real-kernel evidence (Docker ubuntu:24.04, kernel 6.12.76-linuxkit, Landlock ABI v6, bubblewrap 0.9.0), verdict PARITY PROVEN |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `wrap(tier="observe")` | `_scrub_env()` | direct call | WIRED | Line 142 |
| `wrap(tier="confine", platform=darwin)` | `_wrap_macos()` | direct call | WIRED | Line 147 |
| `wrap(tier="confine", platform=linux)` | `_wrap_linux()` | direct call | WIRED | Line 149 |
| `_wrap_macos()` | `build_macos_profile()` | direct call | WIRED | Line 415 |
| `_wrap_linux()` (RUNG 1/2) | `build_linux_bwrap_args()` | direct call | WIRED | Line 465 |
| `_wrap_linux()` (RUNG 1) | `--apply-landlock` shim → `_apply_landlock()` | argv construction, exercised via `__main__` guard | WIRED (shape only, per plan's explicit Phase-25 deferral of live spawn) | Lines 467-477, 485-499 |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| SBX-01 | 23-04 | Linux bwrap+landlock spike proves or documents parity | SATISFIED | `23-SPIKE-LINUX.md` verdict PARITY PROVEN, all 6 sections present, real-kernel evidence. `REQUIREMENTS.md` marks SBX-01 `[x]` / Complete |
| SBX-02 | 23-01, 23-02, 23-03 | `flowstate/sandbox.py` seam + `observe` tier, unit-tested, golden-tested | SATISFIED | `wrap()` implemented per D-04 contract, 54 passing tests including golden tests and the named auth-regression guard. `REQUIREMENTS.md` marks SBX-02 `[x]` / Complete |

No orphaned requirements — REQUIREMENTS.md maps only SBX-01/SBX-02 to Phase 23; both are claimed and satisfied.

### Anti-Patterns Found

None. `grep -nE "TBD|FIXME|XXX|TODO|HACK|PLACEHOLDER"` against `flowstate/sandbox.py` and
`tests/test_sandbox.py` returns no matches. No stub returns (`return null`/`{}`/`[]`), no
console-log-only handlers, no hardcoded-empty-props patterns applicable to this non-UI module.

### Scope Fence Check (explicitly out-of-scope items from 23-CONTEXT.md)

| Check | Result |
|-------|--------|
| No call site wired (`bridge.py`, `pack.py`, `distiller.py`, `tools/base.py`, `discipline.py`, `gsd_vendor.py` import `flowstate.sandbox`) | CONFIRMED CLEAN — zero matches for `from flowstate.sandbox`/`import sandbox`/`sandbox.wrap` in any of the 6 call-site files |
| `ProjectPreferences` (`flowstate/state.py`) gained no `sandbox` field | CONFIRMED CLEAN — zero matches for `sandbox` in `flowstate/state.py` |
| Only `flowstate/sandbox.py`, `tests/test_sandbox.py`, and the spike doc were touched by phase-23 commits | CONFIRMED — `git show --stat` on all 10 phase-23 commits shows changes restricted to those files |

### Security Check

`git grep -n "sk-ant-oat"` across the full repo returns no matches — no OAuth token leaked into
the committed spike artifact or anywhere else in history.

### Behavioral Spot-Checks / Test Execution

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| `tests/test_sandbox.py` suite passes standalone | `uv run python -m pytest tests/test_sandbox.py -q` | `54 passed in 0.54s` (coverage gate fails only because a single-file run can't hit the repo-wide 80% floor — expected and not phase-scoped) | PASS |
| Full repo suite has no regressions from this phase | `uv run python -m pytest tests/ -q --no-cov` | `1288 passed, 1 skipped in 56.45s` | PASS |
| All 10 phase-23 commit hashes exist in history | `git cat-file -e <hash>` × 10 | all OK | PASS |

### Human Verification Required

None. All must-haves are verifiable programmatically: the seam's contract (argv/env transform,
never spawns), the observe-tier non-blocking behavior, the golden profile shapes, and the spike
artifact's presence/content are all confirmable via static inspection and automated tests. The
Linux spike itself was already executed against a real kernel inside Docker (documented with
verbatim captured output) — re-running it is not required for this verification, since the
artifact records concrete, falsifiable evidence (exit codes, errno values, kernel version, ABI
version) rather than a narrative claim.

### Gaps Summary

No gaps. Both requirements (SBX-01, SBX-02) are satisfied with code-level evidence, not just
SUMMARY narrative. The phase goal — retiring the Linux confinement unknown AND shipping the
`wrap()` seam with a non-blocking `observe` tier — is achieved. Scope discipline held: no call
sites were wired and no `ProjectPreferences.sandbox` field was added, matching the phase's
explicit non-goals (reserved for Phase 24).

---

_Verified: 2026-07-12_
_Verifier: Claude (gsd-verifier)_
