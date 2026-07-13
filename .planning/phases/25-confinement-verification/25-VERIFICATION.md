---
phase: 25-confinement-verification
verified: 2026-07-13T00:00:00Z
status: passed
score: 6/6 must-haves verified
overrides_applied: 0
---

# Phase 25: Confinement + Verification Report

**Phase Goal:** The `confine` tier is real and proven — a live `claude --print` succeeds inside the kernel sandbox while writes outside the project root and reads of `~/.ssh` are denied, on both macOS and Linux — and a missing sandbox binary fails loud instead of silently running unconfined.
**Verified:** 2026-07-13
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Under `confine`, when no confinement is achievable (binary genuinely absent, or unsupported platform), `wrap()` RAISES `SandboxUnavailableError` with a per-platform install hint instead of running unconfined (SBX-06) | ✓ VERIFIED | `flowstate/sandbox.py:214-217` (unsupported platform), `:555-558` (macOS, verifies `_find_sandbox_exec()` result `.is_file()`), `:605-607` (Linux, `check_bwrap_available()==False`). Tests: `tests/test_sandbox.py:176,182,192,599,607` — 5 `pytest.raises(SandboxUnavailableError)` sites. All pass. |
| 2 | Partial capability (bwrap present, landlock absent) still degrades WITHIN confinement (RUNG-1→RUNG-2), no raise | ✓ VERIFIED | `_wrap_linux` (`sandbox.py:566-626`): raise only gated on `check_bwrap_available()==False`; landlock-absent branch returns a bwrap-only argv without raising. Regression test present and passing. |
| 3 | Default `observe` tier never raises on any path, including unsupported platforms | ✓ VERIFIED | `wrap()`'s `observe` branch (`sandbox.py:204-205`) returns before any platform dispatch; module docstring re-scopes the "never fails" guarantee explicitly to `observe` + probes. Regression test in `test_sandbox.py` asserts `tier="observe"` on `sys.platform="sunos5"` returns a tuple. |
| 4 | A confined process on macOS can write inside `project_root`, is denied a write outside it (under `$HOME`), and is denied a read of `~/.ssh`, proven by a real (non-mocked) `skip-if-not-darwin` test | ✓ VERIFIED | `tests/test_sandbox_e2e_macos.py` — real `sandbox-exec` via `flowstate.sandbox.wrap(..., tier="confine")`, `_REAL_RUN = subprocess.run` captured pre-monkeypatch. Ran (not skipped, this machine is darwin) — 4/4 passed: write-inside OK, write-outside-`$HOME` denied (file absent), `~/.ssh` read denied (nonzero exit, no listing leaked). |
| 5 | A confined `claude --print` succeeds on macOS via the production `ClaudeBridge(sandbox="confine")` path (Keychain auth survives, API reachable), and the WR-09 temp `.sb` profile is cleaned up on every exit path | ✓ VERIFIED | `flowstate/bridge.py:309-383` — `profile_path` captured immediately after `wrap()` for the confine+darwin+argv-shape case; `finally:` unlinks with `missing_ok=True`, nesting the pre-existing `TimeoutExpired`/`FileNotFoundError` handlers. `tests/test_bridge.py::TestConfineTempProfileCleanup` proves cleanup on success, timeout, FileNotFoundError, and inertness for `observe`. `tests/test_sandbox_e2e_macos.py::TestConfinedClaudeAuthSurvives::test_confined_claude_print_succeeds` ran live on this machine (claude present) and passed — real model output, `result.success is True`. |
| 6 | A confined `claude --print` succeeds on Linux using the EXACT shipped `build_linux_bwrap_args` argv (read-only HOME) + the FILE-based `~/.claude/.credentials.json` credential, with out-of-root-write and `~/.ssh`-read denied, recorded in a committed artifact | ✓ VERIFIED | `.planning/phases/25-confinement-verification/25-SPIKE-LINUX-REPROBE.md` (verdict: FIX-APPLIED). First attempt failed EROFS on claude's own `/tmp/claude-0` scratch dir (genuine filesystem-write failure, not auth) — the D-02 gate's fix branch fired: minimal `--tmpfs /tmp` added to `build_linux_bwrap_args` (`sandbox.py:296-297`), confirmed matching the golden test (`tests/test_sandbox.py::test_matches_golden_shape`, `test_contains_tmpfs_tmp_scratch`). Re-probe: confined `claude --print` exit 0, real output `4`; out-of-root write denied (EROFS, file absent); `~/.ssh` read denied (tmpfs shadow, file invisible). No credential value found in the artifact (`grep -riE "sk-ant|oauth|Bearer |sessionKey"` → no matches). |

**Score:** 6/6 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `flowstate/sandbox.py` | `SandboxUnavailableError` + fail-loud confine dispatch + re-scoped docstring | ✓ VERIFIED | Class defined line 81; raise sites at 214, 555, 605; docstring lines 15-27 document the contract change. |
| `tests/test_sandbox.py` | raise-on-unconfinable tests + preserved never-raise-observe tests | ✓ VERIFIED | 5 `pytest.raises(SandboxUnavailableError)` sites; golden builder test updated for `--tmpfs /tmp`; 73 tests, all pass. |
| `flowstate/gsd_vendor.py` | WR-2 `*_TOKEN` scrub-limitation comment at both wrap sites | ✓ VERIFIED | Lines 331-334, 396-398 — comment-only, no functional change (confirmed by diff review in 25-01-SUMMARY.md and direct grep). |
| `flowstate/bridge.py` | try/finally temp-profile cleanup around confined `subprocess.run` | ✓ VERIFIED | Lines 309-383 — `profile_path` capture + `finally: Path(profile_path).unlink(missing_ok=True)`. |
| `tests/test_bridge.py` | cleanup test proving `.sb` removal on success + error paths | ✓ VERIFIED | `TestConfineTempProfileCleanup` class present; runs and passes. |
| `tests/test_sandbox_e2e_macos.py` | skip-if-not-darwin real-subprocess denial E2E | ✓ VERIFIED | Created; 4 tests (3 denial + 1 double-gated auth); ran live (not skipped) and passed on this darwin machine. |
| `.planning/phases/25-confinement-verification/25-SPIKE-LINUX-REPROBE.md` | committed Linux D-02/D-03 verification artifact | ✓ VERIFIED | Exists; mirrors `23-SPIKE-LINUX.md` structure; verdict FIX-APPLIED; no credential value present. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `wrap()` confine dispatch | `SandboxUnavailableError` | raise when sandbox-exec/bwrap absent or platform unsupported | ✓ WIRED | Confirmed at all 3 sites; tests assert the raise, not just presence. |
| `bridge.py:run()` → `wrap()` | temp `.sb` profile path (`cmd[2]`) | `finally: Path(profile_path).unlink(missing_ok=True)` | ✓ WIRED | Guard correctly scoped to `confine`+`darwin`+`len(cmd)>2`; nests around pre-existing except handlers without replacing them. |
| `tests/test_sandbox_e2e_macos.py` | `flowstate.sandbox.wrap(..., tier="confine")` | real `sandbox-exec` + `subprocess.run`, not mocked | ✓ WIRED | `_REAL_RUN` captured pre-monkeypatch; ran live in this session, 4/4 pass. |
| `25-SPIKE-LINUX-REPROBE.md` | `flowstate.sandbox.build_linux_bwrap_args` | records exact shipped argv + file credential + denial assertions | ✓ WIRED | Argv in the artifact matches `build_linux_bwrap_args`'s actual current output byte-for-byte (verified against the golden test). |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Fail-loud + observe + macOS/bridge unit suite | `uv run python -m pytest tests/test_sandbox.py tests/test_bridge.py tests/test_sandbox_e2e_macos.py -q --no-cov` | 117 passed, 0 failed, 0 skipped (ran live on darwin, including the macOS E2E + auth-survival tests) | ✓ PASS |
| Golden Linux bwrap argv matches shipped fix | `grep` golden test vs. `build_linux_bwrap_args` source | `--tmpfs`, `/tmp` present in both, byte-identical order | ✓ PASS |
| `ruff check` on all phase-touched files | `uv run ruff check flowstate/sandbox.py flowstate/bridge.py flowstate/gsd_vendor.py tests/test_sandbox.py tests/test_bridge.py tests/test_sandbox_e2e_macos.py` | All checks passed | ✓ PASS |
| No debt markers in phase-touched files | `grep -n "TBD\|FIXME\|XXX"` | No matches | ✓ PASS |
| Full suite + coverage gate | `uv run --frozen python -m pytest -q` | 1328 passed, 1 skipped, 1 failed (`test_verdict.py::test_real_mode_no_paired_data_fails_loud` — passes in isolation, fails only under full-suite ordering; unrelated to sandbox/bridge/gsd_vendor; pre-existing per `deferred-items.md`), coverage 91.54% (gate 80%) | ✓ PASS (pre-existing unrelated flake, not a phase-25 regression) |
| No credential value committed | `grep -riE "sk-ant\|oauth\|Bearer \|sessionKey" 25-SPIKE-LINUX-REPROBE.md` | No matches | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| SBX-06 | 25-01 | Fail loud on missing confine binary | ✓ SATISFIED (code) | `SandboxUnavailableError` + 3 raise sites + regression tests. REQUIREMENTS.md correctly shows `[x]` and Traceability = Complete. |
| SBX-05 | 25-02, 25-03, 25-04 | `confine` tier ships macOS SBPL + Linux bwrap; E2E-proven on both platforms | ✓ SATISFIED (code) / ⚠️ STALE (tracking doc) | All code truths (#4, #5, #6 above) verified directly against the codebase and by re-running the test suite in this session. **However**, `.planning/REQUIREMENTS.md` line 21 still shows `- [ ] **SBX-05**` and the Traceability table (line 33) still reads `SBX-05 \| Phase 25 \| Pending` — neither was updated across any of the four plans' summary/tracking commits (confirmed via `git log`/`git show` on `.planning/REQUIREMENTS.md`; the only tracking commit that touched it was 25-01's, which correctly checked off SBX-06 but did not touch SBX-05's line since 25-01 didn't claim it). `.planning/ROADMAP.md`'s phase-level checkbox (line 23, `- [ ] **Phase 25: Confinement + Verification**`) is also still unchecked despite all 4 sub-plans being marked `[x]`. |

**Recommendation (non-blocking):** Before closing v0.9.0, update `.planning/REQUIREMENTS.md` to check off SBX-05 and set its Traceability status to `Complete`, and check off the Phase 25 line in `.planning/ROADMAP.md`. This is a bookkeeping correction only — the underlying SBX-05 work is verified complete and working in the codebase; it does not gate this VERIFICATION's `passed` status but would cause a milestone-close audit (e.g. `gsd-sdk query audit-open`) to flag a false in-flight requirement if left as-is.

### Anti-Patterns Found

None. `ruff check` clean on all phase-touched files; no `TBD`/`FIXME`/`XXX`/placeholder markers; no stub returns; no mocked sandbox-exec/bwrap in the E2E test (verified `_REAL_RUN` captured before any monkeypatch, and the test ran live rather than skipping).

### Human Verification Required

None. The one `checkpoint:human-action` in this phase (25-04 Task 1 — providing a real credential for the Docker container) was already satisfied by the human before the 25-04 executor was spawned, per that plan's SUMMARY, and its outcome (the Docker probe results) is independently verifiable in the committed `25-SPIKE-LINUX-REPROBE.md` artifact, which this verification reviewed directly. The macOS E2E and auth-survival tests were re-run live in this verification session (not merely trusted from SUMMARY) and passed.

### Gaps Summary

No functional gaps. All 6 derived observable truths for SBX-05/SBX-06 are verified directly against the current codebase (not SUMMARY claims): the fail-loud contract is implemented and tested at all 3 no-confinement-achievable sites; partial-capability degrade and `observe`'s never-raise contract are preserved and regression-tested; the macOS confine profile's allow-inside/deny-outside/deny-`~/.ssh` behavior and confined-claude-Keychain-auth-survival were both re-run live on this machine during verification (not just trusted); the Linux Docker re-probe's committed artifact records a real empirical failure (EROFS) → minimal fix (`--tmpfs /tmp`) → re-verified PASS cycle, and the fix is present byte-for-byte in the shipped `build_linux_bwrap_args` with a matching golden test. The only issue found is a **non-blocking documentation staleness**: `.planning/REQUIREMENTS.md`'s SBX-05 checkbox/traceability row and `.planning/ROADMAP.md`'s phase-25 checkbox were never flipped to reflect the (verified-complete) SBX-05 work — flagged above as a recommended pre-milestone-close correction, not a phase gap.

---

_Verified: 2026-07-13_
_Verifier: Claude (gsd-verifier)_
