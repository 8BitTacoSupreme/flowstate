# Phase 24: Thread the Seam + Config - Context

**Gathered:** 2026-07-12
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 24 makes the Phase-23 sandbox seam actually fire on real runs. Two deliverables:

1. **SBX-03 — thread `wrap()` into the agent-directed subprocess sites.** Route the subprocess calls where agent/untrusted content flows through `wrap(cmd, surface, project_root, env, *, tier=<level>)`, preserving `claude` auth/API reachability on every wrapped call.
2. **SBX-04 — the config field.** Add a defaulted `ProjectPreferences.sandbox` level field (`observe` / `confine`), backward-compatible (no state migration), default `observe`, threaded to each wrapped call site as the `tier`.

**Explicitly NOT in this phase:**
- Building the `confine`-tier production profiles for real use / the E2E write-denied+`~/.ssh`-denied denial proof (Phase 25).
- Fail-loud on a missing sandbox binary under `confine` (Phase 25, SBX-06).
- Per-surface network/profile policy — `surface` stays descriptive-only here (Phase 25).
- The two WR-03 production-shape confirmations from the Linux spike (writable HOME under the shipped bwrap argv; file-path `~/.claude/.credentials.json` under confinement) — Phase 25.

Phase 24 wires the seam and the config knob; `observe` (env-scrub) goes live by default, `confine` becomes selectable but its production profiles are hardened/verified in Phase 25.

</domain>

<decisions>
## Implementation Decisions

### SBX-03 — which subprocess sites get wrapped (site coverage)
- **D-01: Wrap the agent-directed sites; leave the internal git-reads bare.** Route through `wrap()`:
  - `flowstate/bridge.py:308` — the `claude --print` call (surface `llm`) — the auth-load-bearing site, MUST be wrapped and MUST preserve auth.
  - `flowstate/distiller.py:92` — the memory→wiki distiller's `claude` call (surface `llm`).
  - `flowstate/tools/base.py:73` — the `ToolAdapter` generic `run_cmd` (surface `tool`).
  - `flowstate/pack.py:115` — repomix, which ingests the whole repo (surface `tool`).
  - `flowstate/gsd_vendor.py:325` and `:376` — npm/parity, which fetch remote (surface `tool`).
  - **Leave BARE:** `flowstate/discipline.py:43/53/63/92` — internal read-only `git` status/branch/count commands. No agent-directed/untrusted input, no injection surface, and confining a read-only `git status` buys nothing; scrubbing `GIT_*` env could only risk breaking them. Record this as a deliberate exclusion (SBX-03 permits "wrapped or left bare per an explicit plan-time decision").

### SBX-03 — `surface` taxonomy
- **D-02: Descriptive surface names now; per-surface policy deferred to Phase 25.** Pass literal surface strings that Phase 25's `confine` profiles will key off: `"llm"` (claude — bridge, distiller), `"tool"` (repomix, npm, adapter run_cmd). Reserve `"vcs"` for git if it is ever wrapped later. The `observe` tier ignores `surface` (as `wrap()` already documents); no network/profile policy is attached to a surface in this phase.

### SBX-04 — config field shape
- **D-03: Single global enum `ProjectPreferences.sandbox: str = "observe"`.** One global level applied to all wrapped sites; allowed values `observe` / `confine` (the two `wrap()` already accepts; unknown values already fail safe to `observe` per WR-01). Defaulted field → no `_migrate_state` change (backward-compatible load). Per-surface granularity (a dict) is deferred until a real need appears.

### SBX-04 — default posture
- **D-04: Default `observe` — env-scrub goes live by default.** Per SBX-04's wording, the default level is `observe`, so every wrapped subprocess receives the secret-denylist-scrubbed env by default. This IS a real runtime change (secret-shaped vars stripped from the claude/repomix/npm/adapter environments), accepted because: the denylist is conservative (only credential-shaped names), `_AUTH_EXEMPT` protects claude's own auth vars, and repomix/npm/the adapters have no legitimate need for secret env. The milestone integrity rule — "observe = env-scrub only, non-blocking, ships without breaking a single existing run" — is the bar; the plan must confirm no wrapped subprocess regresses.

### Config threading (the integration seam)
- The `sandbox` level flows to the `llm` sites via the EXISTING pattern: `ProjectPreferences.sandbox` → `orchestrator._make_bridge` maps it into `BridgeConfig` (mirroring how `enable_prompt_caching_1h` is threaded at `orchestrator.py:115`), and `bridge.py` reads `self.config.sandbox` and passes it as `tier` to `wrap()`. `BridgeConfig` already carries `project_root` (`bridge.py:132`). The non-`llm` sites (pack, distiller, tools/base, gsd_vendor) read the level through their own construction path — the planner determines the cleanest threading for each (they already receive a root / preferences in some form).

### Claude's Discretion
- Exact threading of the level into the non-bridge sites (pack/distiller/tools-base/gsd_vendor) — mirror `_make_bridge`'s pattern; planner's call per call site.
- Whether `wrap()` is called with an explicit `tier=level` at each site or the level is resolved once and passed down — implementation detail, as long as the default remains `observe`.
- Preserving `bridge.py`'s existing env prep ordering: `env = {**os.environ}` → `env.pop("CLAUDECODE")` → set `ENABLE_PROMPT_CACHING_1H` → then `wrap()` scrubs. The 1h-cache var is not secret-shaped so it survives the denylist; confirm CLAUDECODE stays popped and the cache var stays set post-scrub.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### This phase
- `.planning/phases/24-thread-the-seam-config/24-CONTEXT.md` — this file (D-01..D-04).
- `.planning/REQUIREMENTS.md` — SBX-03, SBX-04 + integrity rules (observe non-blocking; auth must survive).

### The seam being wired (Phase 23 output — read to understand the contract)
- `flowstate/sandbox.py` — `wrap(cmd, surface, project_root, env, *, tier="observe") -> (argv, env)`; `_scrub_env` denylist + `_AUTH_EXEMPT`; `surface` is currently reserved/ignored by `observe`.
- `.planning/phases/23-linux-parity-core-seam/23-CONTEXT.md` — the Phase-23 locked decisions the seam embodies.
- `.planning/phases/23-linux-parity-core-seam/23-SPIKE-LINUX.md` — the PARITY PROVEN verdict + the two WR-03 production-shape caveats that are Phase-25 (not Phase-24) concerns.

### Integration targets (the call sites + config)
- `flowstate/bridge.py` — `:130` `BridgeConfig` (has `project_root`), `:300-320` the env-prep + `subprocess.run` at `:308` (the `llm` site).
- `flowstate/orchestrator.py:105` — `_make_bridge`, the ProjectPreferences→BridgeConfig mapping pattern to mirror (`:115` `enable_prompt_caching_1h` is the closest analog).
- `flowstate/state.py:38` — `ProjectPreferences`, where the defaulted `sandbox` field lands (no migration).
- `flowstate/distiller.py:92`, `flowstate/tools/base.py:73`, `flowstate/pack.py:115`, `flowstate/gsd_vendor.py:325/376` — the other wrapped sites.
- `flowstate/discipline.py:43/53/63/92` — the git-read sites deliberately LEFT BARE (D-01).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `orchestrator._make_bridge` (`:105-116`) already maps `ProjectPreferences` → `BridgeConfig` field-by-field — the exact pattern to extend for `sandbox` (add one kwarg line like `:115`).
- `wrap()` is complete and contract-stable from Phase 23; Phase 24 only calls it. `observe` (the default) is `return cmd, _scrub_env(env)` — a pure transform, no spawn.
- `BridgeConfig.project_root` (`bridge.py:132`) already exists — `wrap()`'s `project_root` arg is available at the `llm` site with no plumbing.

### Established Patterns
- Defaulted Pydantic fields on `ProjectPreferences` load backward-compatibly with zero `_migrate_state` change — every field added since v0.3 followed this (e.g. `enable_prompt_caching_1h`, `wiki_layer`). `sandbox: str = "observe"` follows suit.
- `bridge.py`'s env prep (`{**os.environ}` → pop CLAUDECODE → set cache var) is the canonical env-mutation point; `wrap()`'s scrub composes onto the end of it.

### Integration Points
- The seam threads: `ProjectPreferences.sandbox` → `_make_bridge`/BridgeConfig (llm sites) or the site's own construction (tool sites) → `wrap(..., tier=level)` → `(argv, env)` → the existing `subprocess.run(argv, env=env, ...)`. Each site's diff is ~2 lines (D-04 tuple contract), no control-flow change.

</code_context>

<specifics>
## Specific Ideas

- The `bridge.py:308` `llm` site is the load-bearing one: its Phase-23 spike (macOS + Linux) proved confined `claude` auth survives, so wrapping it at `observe` (env-scrub only, argv untouched) is strictly safe — the only observable change is secret-shaped env vars (not `_AUTH_EXEMPT`) no longer reaching the claude subprocess.
- Leaving `discipline.py` git-reads bare is deliberate and should be a visible, commented exclusion, not a silent omission — a future reviewer should see it was decided, not forgotten.

</specifics>

<deferred>
## Deferred Ideas

- **`confine`-tier production profiles + E2E denial proof** (write-outside-root denied, `~/.ssh` read denied, auth survives) — Phase 25 (SBX-05).
- **Fail-loud on missing sandbox binary under `confine`** — Phase 25 (SBX-06).
- **WR-03 production-shape confirmations** (writable HOME under the shipped Linux bwrap argv; file-path `~/.claude/.credentials.json` under confinement) — Phase 25.
- **Per-surface network/profile policy** and a per-surface config dict — deferred; `surface` stays descriptive-only, config stays a single global enum (D-02, D-03).
- **Wrapping the `discipline.py` git-reads / a `vcs` confine profile** — out of scope by D-01; revisit only if a real threat surfaces there.

</deferred>

---

*Phase: 24-Thread the Seam + Config*
*Context gathered: 2026-07-12*
