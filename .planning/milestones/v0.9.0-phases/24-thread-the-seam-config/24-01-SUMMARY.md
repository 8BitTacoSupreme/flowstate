---
phase: 24-thread-the-seam-config
plan: 01
subsystem: infra
tags: [sandbox, security, subprocess, config, claude-cli, pydantic]
status: complete

# Dependency graph
requires:
  - phase: 23-linux-parity-core-seam
    provides: "flowstate/sandbox.py wrap(cmd, surface, project_root, env, *, tier) — the observe env-scrub + confine platform-confinement seam, contract-stable, not yet wired to any live caller"
provides:
  - "ProjectPreferences.sandbox: str = 'observe' defaulted config field (SBX-04), no _migrate_state change, backward-compatible load"
  - "BridgeConfig.sandbox field + orchestrator._make_bridge unconditional mapping (mirrors enable_prompt_caching_1h)"
  - "bridge.py's claude --print call (the auth-load-bearing llm site) routed through wrap('llm', ...)"
  - "distiller.py's claude densify call routed through wrap('llm', ...) with tier resolved from saved preferences"
affects: [25-confine-tier-production-profiles, sandbox, bridge, distiller, orchestrator]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Defaulted ProjectPreferences field -> orchestrator._make_bridge unconditional kwargs mapping -> BridgeConfig field (the config-threading spine every wrap()-consuming site mirrors)"
    - "wrap(cmd, surface, project_root, env, *, tier=level) inserted immediately before subprocess.run, after all env-prep mutations, so the scrub composes onto the end of existing env logic without reordering it"

key-files:
  created: []
  modified:
    - flowstate/state.py
    - flowstate/bridge.py
    - flowstate/orchestrator.py
    - flowstate/distiller.py
    - tests/test_state.py
    - tests/test_orchestrator.py
    - tests/test_bridge.py
    - tests/test_distiller.py

key-decisions:
  - "Added a _make_bridge sandbox-mapping test to tests/test_orchestrator.py (not listed in Task 1's <files>) — needed to cover the required behavior 'preferences.sandbox==confine produces BridgeConfig.sandbox==confine' and mirrors the existing enable_prompt_caching_1h test pair 1:1."
  - "distiller._densify gained a required `root: Path` positional parameter (no default) since wrap() needs project_root at every call site; the single production call site in `main` already has `root` in scope, so this is a pure signature extension with no default-value ambiguity."

requirements-completed: [SBX-03, SBX-04]

# Metrics
duration: ~20min
completed: 2026-07-12
---

# Phase 24 Plan 01: Thread the Seam + Config Summary

**Defaulted `ProjectPreferences.sandbox` config field threaded into both auth-load-bearing `claude`-spawning sites (bridge.py, distiller.py) via `wrap("llm", ...)`, with claude auth proven to survive the env scrub at both sites.**

## Performance

- **Duration:** ~20 min
- **Started:** 2026-07-12T17:36Z (approx, first task commit)
- **Completed:** 2026-07-12T17:40Z (last task commit) + verification/summary pass
- **Tasks:** 3
- **Files modified:** 8 (4 source, 4 test)

## Accomplishments
- `ProjectPreferences.sandbox: str = "observe"` lands as a defaulted field with zero `_migrate_state` change — proven backward-compatible against an old preferences blob missing the key
- `BridgeConfig.sandbox` + `_make_bridge` unconditional kwargs mapping complete the config-threading spine (`ProjectPreferences.sandbox` -> `BridgeConfig.sandbox`), mirroring the existing `enable_prompt_caching_1h` pattern at `orchestrator.py:115`
- `bridge.py`'s `claude --print` call (the highest-risk, auth-load-bearing site) now routes through `wrap("llm", ...)`; auth vars (`ANTHROPIC_API_KEY`, `CLAUDE_CODE_OAUTH_TOKEN`, `CLAUDE_CONFIG_DIR`) survive the scrub, `CLAUDECODE` stays popped, `ENABLE_PROMPT_CACHING_1H` stays set, credential-shaped vars (e.g. `AWS_SECRET_ACCESS_KEY`) are dropped under the new default `observe` tier
- `distiller.py`'s `claude` densify call now builds an explicit scrubbed env via `wrap("llm", ...)` (it previously inherited `os.environ` unscoped with no `env=` kwarg at all); the sandbox level is resolved once per run from `load_state(root).preferences.sandbox` and threaded down as `tier`; the existing "any subprocess failure returns original article text unchanged" degradation contract is intact

## Task Commits

Each task followed the RED/GREEN TDD cycle with separate commits:

1. **Task 1: Add the defaulted sandbox config field (SBX-04) + BridgeConfig field + _make_bridge mapping**
   - `15a9a36` (test) — failing tests for `ProjectPreferences.sandbox`/`BridgeConfig.sandbox`/`_make_bridge` mapping
   - `ceadad0` (feat) — the defaulted fields + unconditional kwargs mapping
2. **Task 2: Wrap the bridge.py:308 claude call at surface "llm"**
   - `1a209f2` (test) — failing test asserting auth-survival + env-prep-ordering + credential-scrub at the `bridge.py` llm site
   - `6452ab5` (feat) — the `wrap("llm", ...)` call inserted before `subprocess.run`
3. **Task 3: Wrap the distiller.py:92 claude densify call at surface "llm" and thread the tier**
   - `35e3d0a` (test) — failing tests for `_densify`'s explicit scrubbed env + `main`'s tier resolution from saved preferences
   - `59e1f13` (feat) — `_densify` explicit `wrap("llm", ...)` env + `main` resolving `tier` from `load_state(root).preferences.sandbox`

**Plan metadata:** (this commit) — SUMMARY + STATE/ROADMAP/REQUIREMENTS updates

_Note: every task in this plan used `tdd="true"`; each has a distinct RED (test) commit followed by a GREEN (feat) commit. No REFACTOR commit was needed — implementations were minimal 2-4 line diffs matching the plan's stated ~2-line-diff contract._

## Files Created/Modified
- `flowstate/state.py` — `ProjectPreferences.sandbox: str = "observe"` defaulted field, positioned after `wiki_layer`; no `_migrate_state`/`load_state` change
- `flowstate/bridge.py` — `BridgeConfig.sandbox: str = "observe"` field; `wrap` imported from `flowstate.sandbox`; one `wrap("llm", ...)` call inserted after the existing env-prep block, before `subprocess.run`
- `flowstate/orchestrator.py` — `_make_bridge` gains one unconditional `kwargs["sandbox"] = preferences.sandbox` line inside the `if preferences:` block, directly mirroring the `enable_prompt_caching_1h` mapping
- `flowstate/distiller.py` — `_densify` gains `root: Path` and keyword-only `tier: str = "observe"` params, builds an explicit scrubbed env via `wrap("llm", root, {**os.environ}, tier=tier)` and passes it to `subprocess.run`; `main` resolves `tier = load_state(root).preferences.sandbox` once and threads `root=root, tier=tier` into the single `_densify` call site
- `tests/test_state.py` — sandbox default, roundtrip, and backward-compat-load (missing key) tests
- `tests/test_orchestrator.py` — `_make_bridge` sandbox-mapping tests (confine threads through; no-preferences default stays observe)
- `tests/test_bridge.py` — `TestSandboxWrapLlmSite`: auth-survival + ordering + credential-scrub test via a patched `subprocess.run` capturing the `env=` kwarg
- `tests/test_distiller.py` — `TestDensifySandboxWrap`: auth-survival/credential-scrub and subprocess-failure-degradation tests; `test_distill_main_resolves_tier_from_saved_preferences` covering the tier-resolution path

## Decisions Made
- Extended `tests/test_orchestrator.py` (not in Task 1's declared `<files>`) to directly test the `_make_bridge` sandbox mapping, since that behavior is part of Task 1's required `<behavior>` block and the file already hosts the exact analogous `enable_prompt_caching_1h` test pair — adding tests elsewhere would have split coverage of one code path across two unrelated files.
- `_densify` took a required (no-default) `root: Path` parameter rather than an optional one, since `wrap()` needs a concrete `project_root` at every call and the only production call site already has `root` in scope — an optional/`None` default would just push the same requirement into a runtime check inside the function body for no benefit.

## Deviations from Plan

None - plan executed exactly as written. The one test-file addition beyond the plan's declared `<files>` list (`tests/test_orchestrator.py`) is documented above under Decisions Made — it is coverage for a `<behavior>` line explicitly required by the plan, not new scope.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Threat Model Disposition (from 24-01-PLAN.md)

| Threat ID | Disposition | Verified |
|-----------|-------------|----------|
| T-24-01 (DoS / availability regression under default observe) | mitigate | `tests/test_bridge.py::TestSandboxWrapLlmSite` + `tests/test_distiller.py::TestDensifySandboxWrap` assert only credential-shaped vars are dropped; full `test_bridge.py`/`test_distiller.py` suites stay green (36 + 26 tests respectively) |
| T-24-02 (auth loss at either claude-spawning site) | mitigate | Explicit tests at both `bridge.py` and `distiller.py` assert `ANTHROPIC_API_KEY`/`CLAUDE_CODE_OAUTH_TOKEN`/`CLAUDE_CONFIG_DIR` survive the scrub |
| T-24-03 (env-ordering regression in bridge.py) | mitigate | `test_default_observe_scrubs_secrets_preserves_auth_and_ordering` asserts `CLAUDECODE` stays popped and `ENABLE_PROMPT_CACHING_1H` stays set post-scrub |
| T-24-04 (silent behavior flip for existing users, default observe going live) | accept | Documented in the `ProjectPreferences.sandbox` field comment and this SUMMARY; env-scrub is conservative (credential-shaped names only) and non-blocking |
| T-24-SC (package-install tampering) | accept | No package installs performed in this plan |

## Next Phase Readiness
- The config-threading spine (`ProjectPreferences.sandbox` -> `BridgeConfig`/site-local `tier` -> `wrap(..., tier=...)`) is proven end-to-end at both `llm` sites and ready to mirror for the remaining `tool`-surface sites (`tools/base.py`, `pack.py`, `gsd_vendor.py`) in plan 24-02.
- `discipline.py`'s git-read sites remain deliberately unwrapped per D-01 — no action needed from this plan.
- Full test suite: 1312 passed, 1 skipped, 91.35% coverage (gate: 80%) — no regressions introduced.

---
*Phase: 24-thread-the-seam-config*
*Completed: 2026-07-12*

## Self-Check: PASSED

All created/modified source files confirmed present on disk; all 6 task commit hashes (15a9a36, ceadad0, 1a209f2, 6452ab5, 35e3d0a, 59e1f13) confirmed present in git log.
