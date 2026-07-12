---
phase: 24-thread-the-seam-config
verified: 2026-07-12T22:30:00Z
status: passed
score: 8/8 must-haves verified
overrides_applied: 0
---

# Phase 24: Thread the Seam + Config Verification Report

**Phase Goal:** The agent-directed subprocess sites are routed through the Phase-23 `wrap()` seam (auth preserved), and `ProjectPreferences` gains a defaulted `sandbox` level field (observe/confine, no migration); env-scrub goes live by default, confinement stays opt-in.

**Verified:** 2026-07-12
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `bridge.py:308` (claude --print, the auth-load-bearing site) is routed through `wrap()` at surface "llm" | VERIFIED | `flowstate/bridge.py:309` — `cmd, env = wrap(cmd, "llm", self.config.project_root, env, tier=self.config.sandbox)`, inserted after CLAUDECODE pop + cache-var set, before `subprocess.run` at :313 |
| 2 | `distiller.py:92` (claude densify call) is routed through `wrap()` at surface "llm" with tier resolved from saved preferences | VERIFIED | `flowstate/distiller.py:96` — `wrap(cmd, "llm", root, {**os.environ}, tier=tier)`; `main()` line 218 resolves `tier = load_state(root).preferences.sandbox` once, threaded into the single `_densify` call site |
| 3 | `tools/base.py:73` (ToolAdapter.run_cmd) is routed through `wrap()` at surface "tool" | VERIFIED | `flowstate/tools/base.py:78` — `wrap(cmd, "tool", self.root, {**os.environ}, tier=self.sandbox)`; `self.sandbox` threaded via `__init__` kwarg (default "observe"); `orchestrator.py:271,293` construct `ResearchAdapter`/`StrategyAdapter` with `sandbox=state.preferences.sandbox` |
| 4 | `pack.py:115` (repomix) is routed through `wrap()` at surface "tool" | VERIFIED | `flowstate/pack.py:119` — `wrap(cmd, "tool", root, {**os.environ}, tier=sandbox)`; `run_pack(root, *, compress=False, sandbox="observe")`; both CLI callers (`kickoff` :146, `pack` :787) pass `sandbox=state.preferences.sandbox` |
| 5 | `gsd_vendor.py:325/376` (npm install + node parity) are routed through `wrap()` at surface "tool", default observe, not project-scoped | VERIFIED | `flowstate/gsd_vendor.py:330` and `:386-391` both call `wrap(cmd, "tool", Path.cwd(), {**os.environ})` — no `tier=` kwarg passed, so default "observe" applies; commented rationale confirms `refresh()` has no `root`/`resolve_root()` in its caller chain (`gsd_version --refresh`) |
| 6 | `discipline.py:43/53/63/92` (internal git-read + pytest sites) are deliberately LEFT BARE with a visible SBX-03/D-01 comment | VERIFIED | `flowstate/discipline.py:41-49` (block comment above `_read_git_state`'s three `subprocess.run` calls at :52/:62/:72) and `:101-102` (comment above `_run_project_tests`'s call at :103) — both reference SBX-03/D-01 explicitly; zero `wrap()` import added to this file |
| 7 | No agent-directed subprocess site anywhere in `flowstate/` is unwrapped-and-unmarked | VERIFIED | `grep -rn "subprocess\.(run|Popen|call|check_)" flowstate/` → every match is one of: wrapped (bridge/distiller/tools-base/pack/gsd_vendor), bare-with-comment (discipline.py ×4), or the sandbox seam's own internal bwrap-availability probe (`sandbox.py:441`, part of the confinement mechanism itself, not an agent-directed call site) |
| 8 | `ProjectPreferences.sandbox` is a defaulted field (default "observe"); no `_migrate_state` change; backward-compat load proven by test | VERIFIED | `flowstate/state.py:55` — `sandbox: str = "observe"`; `git show ceadad0 -- flowstate/state.py` shows a pure 4-line comment+field addition, zero touch to `_migrate_state` (confirmed function body unchanged); `tests/test_state.py::test_load_state_without_sandbox_field_defaults_observe` constructs a raw v0.4.0 JSON blob with `sandbox` intentionally absent and asserts it loads with `sandbox == "observe"` and `version == "0.4.0"` (no migration bump) |

**Score:** 8/8 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `flowstate/state.py` | `ProjectPreferences.sandbox: str = "observe"` | VERIFIED | Line 55, defaulted, commented with SBX-04/D-03/D-04 rationale |
| `flowstate/bridge.py` | `BridgeConfig.sandbox` field + `wrap("llm", ...)` at the claude call | VERIFIED | Line 143 (`sandbox: str = "observe"`), line 309 (`wrap` call) |
| `flowstate/orchestrator.py` | `_make_bridge` maps `preferences.sandbox` → `BridgeConfig.sandbox`; adapters constructed with `sandbox=` | VERIFIED | Line 117 (`_make_bridge`), lines 271/293 (adapter construction) |
| `flowstate/distiller.py` | `_densify` wraps at "llm"; `main` resolves tier from saved preferences | VERIFIED | Lines 82-96 (`_densify` signature + wrap call), line 218 (`main` tier resolution) |
| `flowstate/tools/base.py` | `ToolAdapter.run_cmd` wraps at "tool" | VERIFIED | Lines 36/48 (`sandbox` param + attr), line 78 (wrap call) |
| `flowstate/pack.py` | `run_pack` wraps repomix at "tool" | VERIFIED | Line 77 (`sandbox` param), line 119 (wrap call) |
| `flowstate/gsd_vendor.py` | `refresh()` wraps npm + node parity at "tool", default observe | VERIFIED | Lines 330, 386-391 (both wrap calls, no tier kwarg → default observe) |
| `flowstate/discipline.py` | Bare git/pytest sites with visible SBX-03/D-01 exclusion comments | VERIFIED | Lines 41-49, 101-102 |
| `flowstate/cli.py` | `kickoff`/`pack` commands thread `sandbox=state.preferences.sandbox` into `run_pack` | VERIFIED | Lines 146, 787 |
| `flowstate/sandbox.py` | UNMODIFIED (scope fence — Phase 24 only calls `wrap()`, doesn't change it) | VERIFIED | `git log` shows last touches are all Phase-23 commits (`a6f547a` and earlier); no Phase-24 commit touches this file |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `ProjectPreferences.sandbox` | `BridgeConfig.sandbox` | `orchestrator._make_bridge` unconditional kwargs mapping | WIRED | `orchestrator.py:117`; test `tests/test_orchestrator.py` covers confine-threads-through + no-preferences-defaults-observe |
| `BridgeConfig.sandbox` | `wrap(..., tier=...)` at bridge.py llm site | `self.config.sandbox` read directly | WIRED | `bridge.py:309` |
| `load_state(root).preferences.sandbox` | `_densify(..., tier=...)` | `main()` one-time resolution | WIRED | `distiller.py:218,226`; test `test_distill_main_resolves_tier_from_saved_preferences` |
| `state.preferences.sandbox` | `ResearchAdapter`/`StrategyAdapter` `sandbox=` kwarg | orchestrator adapter construction | WIRED | `orchestrator.py:271,293` |
| `ToolAdapter.sandbox` | `wrap(..., tier=self.sandbox)` at run_cmd | direct attribute read | WIRED | `tools/base.py:78` |
| `state.preferences.sandbox` | `run_pack(..., sandbox=...)` | CLI command construction | WIRED | `cli.py:146,787` |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Auth vars survive scrub at bridge.py llm site + env-ordering preserved | `tests/test_bridge.py::TestSandboxWrapLlmSite::test_default_observe_scrubs_secrets_preserves_auth_and_ordering` | Asserts `ANTHROPIC_API_KEY`/`CLAUDE_CODE_OAUTH_TOKEN`/`CLAUDE_CONFIG_DIR` present, `CLAUDECODE` absent, `ENABLE_PROMPT_CACHING_1H=="1"`, `AWS_SECRET_ACCESS_KEY` absent — all pass | PASS |
| Auth vars survive scrub at distiller.py llm site | `tests/test_distiller.py::TestDensifySandboxWrap::test_densify_scrubs_secrets_preserves_auth` | Asserts `ANTHROPIC_API_KEY` present, `AWS_SECRET_ACCESS_KEY` absent — pass | PASS |
| Backward-compat load of old flowstate.json missing `sandbox` key | `tests/test_state.py::test_load_state_without_sandbox_field_defaults_observe` | Asserts `loaded.preferences.sandbox == "observe"` and `version == "0.4.0"` (no migration bump) — pass | PASS |
| Full suite green with default observe live everywhere | `uv run python -m pytest tests/ -q --cov=flowstate --cov-fail-under=80` | 1315 passed, 1 skipped, 91.37% coverage (gate 80%) | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| SBX-03 | 24-01, 24-02 | Agent-directed subprocess sites routed through `wrap()`, auth preserved; git-read/npm sites wrapped or bare per explicit decision | SATISFIED | All 8 sites accounted for (2 llm, 4 tool wrapped, 4 discipline.py bare-with-comment); grep confirms no unwrapped-and-unmarked site; auth-survival tests pass at both llm sites |
| SBX-04 | 24-01 | `ProjectPreferences.sandbox` defaulted field, backward-compatible, no migration, default observe | SATISFIED | Field present, `_migrate_state` untouched (confirmed via `git show`), explicit backward-compat test passes |

REQUIREMENTS.md confirms `[x] SBX-03` / `[x] SBX-04` and traceability table lines 30-31 marked `Complete` for Phase 24 — consistent with code evidence above (not taken on faith; independently verified per-site).

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| — | — | None found | — | Grep for `TBD\|FIXME\|XXX\|TODO\|HACK\|PLACEHOLDER` across all 9 phase-modified source files returned zero matches |

### Scope Fence Check

- `flowstate/sandbox.py` — confirmed unmodified by any Phase-24 commit (`git log` shows last touch is Phase-23's `a6f547a`).
- No `confine`-tier hardening, fail-loud behavior, or WR-03 production-shape work found in any Phase-24 diff — matches the phase's explicit "NOT in this phase" boundary.
- `git diff --stat` across all 10 Phase-24 commits touches exactly the files declared in both SUMMARYs (state/bridge/orchestrator/distiller/tools-base/pack/gsd_vendor/cli/discipline + their test files) — no unrelated files modified.

### Human Verification Required

None. This phase's behavior (subprocess env transformation, config field defaulting, backward-compatible load) is fully verifiable via static code inspection, git history, and automated tests — no UI, real-time, or external-service behavior requiring human judgment.

### Gaps Summary

No gaps found. All 8 observable truths verified against actual code (not SUMMARY claims): every declared subprocess site was independently located and its wrap-or-bare-with-comment status confirmed by reading the surrounding code, not by trusting the SUMMARY's site inventory table. The `_migrate_state` no-change claim was independently verified via `git show` on the exact commit rather than trusting the SUMMARY's assertion. Auth-survival was verified by reading the actual test assertions, not just their names. Full test suite run independently in this verification session (not copied from SUMMARY) reproduced the identical 1315 passed / 1 skipped / 91.37% coverage figures.

---

_Verified: 2026-07-12_
_Verifier: Claude (gsd-verifier)_
