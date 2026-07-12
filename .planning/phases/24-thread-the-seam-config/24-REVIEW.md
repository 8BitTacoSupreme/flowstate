---
phase: 24-thread-the-seam-config
reviewed: 2026-07-12T22:00:26Z
depth: standard
files_reviewed: 9
files_reviewed_list:
  - flowstate/bridge.py
  - flowstate/distiller.py
  - flowstate/tools/base.py
  - flowstate/tools/research.py
  - flowstate/tools/strategy.py
  - flowstate/tools/gsd_adapter.py
  - flowstate/pack.py
  - flowstate/gsd_vendor.py
  - flowstate/orchestrator.py
  - flowstate/state.py
  - flowstate/cli.py
  - flowstate/discipline.py
findings:
  critical: 0
  warning: 2
  info: 3
  total: 5
status: issues_found
---

# Phase 24: Code Review Report

**Reviewed:** 2026-07-12T22:00:26Z
**Depth:** standard
**Files Reviewed:** 9 source + 8 test files (diff 0043488..HEAD)
**Status:** issues_found

## Summary

Phase 24 threads `sandbox.py`'s `wrap()` seam into the five agent-directed subprocess
sites (`bridge.py`, `distiller.py`, `tools/base.py`, `pack.py`, `gsd_vendor.py`) and adds
the defaulted `ProjectPreferences.sandbox` / `BridgeConfig.sandbox` config field. The
load-bearing site — `bridge.py`'s `claude --print` call — is correct: env-prep ordering
is preserved (`CLAUDECODE` popped and `ENABLE_PROMPT_CACHING_1H` set **before** `wrap()`
scrubs, matching the documented contract), the scrubbed env — not the raw env — is the
one passed to `subprocess.run`, and `_AUTH_EXEMPT` covers all three vars `bridge.py`
actually needs (`ANTHROPIC_API_KEY`, `CLAUDE_CODE_OAUTH_TOKEN`, `CLAUDE_CONFIG_DIR`). No
site changes argv/cwd/kwargs beyond the env swap; `pack.py`/`gsd_vendor.py`/
`tools/base.py`'s wrapped `subprocess.run` calls are otherwise byte-identical to their
pre-Phase-24 shape. `discipline.py`'s bare exclusion is a documented, deliberate decision
per D-01, not a silent omission. New tests (`test_bridge.py`, `test_pack.py`,
`test_gsd_vendor.py`, `test_distiller.py`, `test_tools_extended.py`, `test_state.py`,
`test_orchestrator.py`) genuinely exercise the env-scrub behavior (spy on
`subprocess.run`, assert credential-shaped vars are dropped and `PATH`/auth vars
survive) rather than being weakened to pass; ran the full changed-file test set locally
— 225 passed, 0 failed.

Two real gaps found, both in the **config-threading completeness** dimension (D-03's
"threaded to each wrapped call site as the tier" contract), not in the `observe` env-scrub
mechanism itself:

1. `tools/base.py`'s lazily-constructed `ClaudeBridge` (the `.bridge` property) does not
   thread `self.sandbox` into the `BridgeConfig` it builds — a latent tier-downgrade trap,
   currently unreachable in production since `orchestrator.py` always passes an explicit,
   correctly-configured shared `bridge`.
2. `ResearchAdapter`/`StrategyAdapter` are constructed with `sandbox=state.preferences.sandbox`
   but that attribute is never read by either adapter (neither calls `run_cmd`) — dead
   threading, not a correctness bug, but worth a maintainer's attention as unreachable/
   misleading state.

No Critical/Blocker findings — auth survives, env-prep ordering is correct, and
`observe` never breaks a wrapped subprocess in the reviewed code paths.

## Warnings

### WR-01: `ToolAdapter.bridge`'s lazy-construction path doesn't thread `self.sandbox`

**File:** `flowstate/tools/base.py:50-55`
**Issue:** The `bridge` property builds a fallback `ClaudeBridge` when no bridge was
injected at construction time:

```python
@property
def bridge(self) -> ClaudeBridge:
    if self._bridge is None:
        config = BridgeConfig(project_root=self.root)
        self._bridge = ClaudeBridge(config=config, dry_run=self.dry_run)
    return self._bridge
```

`self.sandbox` (set in `__init__`, threaded correctly into `run_cmd`'s `wrap("tool", ...)`
call at line 78) is never passed into this `BridgeConfig`, so `BridgeConfig.sandbox` falls
back to its dataclass default `"observe"` regardless of what `self.sandbox` was set to.
If a caller ever constructs a `ToolAdapter` subclass with `sandbox="confine"` and does
*not* inject an explicit `bridge=` (i.e. relies on this lazy path — which is exactly what
`test_bridge_auto_created` in `test_tools_extended.py` exercises, just not with a non-
default tier), the adapter's `llm`-surface calls silently run at `observe` instead of the
requested `confine` tier. Currently dead in the two live production callers
(`orchestrator.run_pipeline` always passes an explicit `bridge=bridge` built by
`_make_bridge`, which does thread `sandbox` correctly — see `orchestrator.py:105-119`),
but it is a real inconsistency with the "thread the level into the site" contract this
phase establishes, and no test asserts the lazy path threads the tier at all.
**Fix:**
```python
@property
def bridge(self) -> ClaudeBridge:
    if self._bridge is None:
        config = BridgeConfig(project_root=self.root, sandbox=self.sandbox)
        self._bridge = ClaudeBridge(config=config, dry_run=self.dry_run)
    return self._bridge
```

### WR-02: `refresh()`'s npm install site scrubs `_TOKEN`-suffixed vars unconditionally, which can silently break authenticated npm registries

**File:** `flowstate/gsd_vendor.py:316-333`
**Issue:** `_DENY_SUFFIXES` in `sandbox.py` includes `"_TOKEN"` (Phase 23 scope, not
re-reviewed here), and `refresh()`'s `npm install` call is wrapped at default `observe`
with no override. A common CI/private-registry pattern is `.npmrc` with
`//registry.npmjs.org/:_authToken=${NPM_TOKEN}` — under Phase-24's now-live-by-default
`observe` scrub, `NPM_TOKEN` (and any other `*_TOKEN` var an org uses for registry auth)
is silently stripped before `npm install` runs, which would surface as a confusing
401/403 from npm rather than an obvious "env was scrubbed" message. For the current
in-repo use case (installing the public `get-shit-done-cc` package) this is a non-issue,
but it's exactly the kind of "does default-observe break a real npm install" regression
this phase's integrity rule (D-04) asks reviewers to rule out, and it's not called out
anywhere in the 24-CONTEXT.md decisions or code comments the way the `observe`-tier
rationale is for the other sites.
**Fix:** No code change required for the current use case; recommend a one-line comment
at the `refresh()` wrap call site (mirroring the existing "not project-scoped" comment)
noting that `observe`'s denylist will strip any `*_TOKEN`-shaped registry-auth var, so a
private-registry refresh needs `FLOWSTATE_NPM_BIN` pointed at a pre-authenticated npm
config or an env passthrough exception — otherwise a future maintainer debugging a failed
private-registry refresh has no signal that the scrub, not npm itself, is the cause.

## Info

### IN-01: `ResearchAdapter`/`StrategyAdapter` thread `sandbox=` into a constructor field neither adapter reads

**File:** `flowstate/orchestrator.py:265-294`, `flowstate/tools/research.py`,
`flowstate/tools/strategy.py`
**Issue:** `orchestrator.run_pipeline` passes `sandbox=state.preferences.sandbox` when
constructing `ResearchAdapter` and `StrategyAdapter` (orchestrator.py:271, :293).
Neither adapter calls `self.run_cmd(...)` — both exclusively use `self.bridge.run(...)`,
where `self.bridge` is the shared, already-correctly-configured bridge built by
`_make_bridge`. So `self.sandbox` on these two adapter instances is write-only state:
set, never read. `GSDAdapter` (orchestrator.py:311) is constructed *without* `sandbox=`
at all, which is consistent (it never touches subprocess or bridge either), highlighting
the inconsistency — two adapters get a kwarg they don't use, one doesn't get it at all,
and none of the three would actually be affected either way today.
**Fix:** No functional fix needed; either drop the `sandbox=` kwarg from the
`ResearchAdapter`/`StrategyAdapter` constructions (since it's unused) or add a short
comment noting it's forwarded for future `run_cmd` use, matching the existing
"future-proofs the contract" comment already used for `prior_knowledge` on the `gsd`
construction a few lines below (orchestrator.py:309-310).

### IN-02: `distiller.py`'s standalone claude invocation doesn't pop `CLAUDECODE`, unlike `bridge.py`

**File:** `flowstate/distiller.py:82-105`
**Issue:** `bridge.py:304` explicitly does `env.pop("CLAUDECODE", None)` before wrapping,
with the comment "Unset CLAUDECODE env var to allow nested invocation." `distiller.py`'s
`_densify()` builds its env as `{**os.environ}` and passes it straight into `wrap()`
without the same pop — this is pre-existing behavior (confirmed via `git show 59e1f13`;
before Phase 24, `_densify` didn't pass `env=` to `subprocess.run` at all, so it inherited
the full untouched parent env, which also included `CLAUDECODE` if set). Phase 24 didn't
introduce a regression here, but it did touch this exact function to add explicit env
threading, and the review's stated focus is specifically "does the wrapped claude call
still receive its real credentials... any way default-observe breaks a real `claude
--print`" — if `flowstate distill --llm` is ever invoked from within an already-running
Claude Code session (`CLAUDECODE` set in the parent env), the nested `claude --print`
densify call may behave differently than the same call issued via `bridge.py` from the
same context, since one path pops the var and the other doesn't.
**Fix:** Consider mirroring `bridge.py`'s pop for consistency, since both sites now share
the identical wrap-and-run shape:
```python
def _densify(article_text, claude, model, root, *, tier="observe"):
    ...
    env_in = {**os.environ}
    env_in.pop("CLAUDECODE", None)
    cmd, env = wrap(cmd, "llm", root, env_in, tier=tier)
```
Low priority — pre-existing, not a Phase-24 regression, and `distiller --llm` is not on
the primary pipeline path.

### IN-03: `ProjectPreferences.sandbox` has no CLI/interview surface

**File:** `flowstate/state.py:52-55`, `flowstate/interview.py`, `flowstate/cli.py`
**Issue:** The new `sandbox` field can only be set by hand-editing `flowstate.json` — no
`flowstate config` option or interview question exposes it. This appears to be an
intentional scope boundary per 24-CONTEXT.md (SBX-04 only asks for the config field +
threading; `confine`'s production profiles and general availability are Phase 25), so
this is not a defect, just worth confirming the boundary is deliberate before Phase 25
adds `confine`-tier hardening without also adding a way for a user to opt in short of
editing JSON by hand.
**Fix:** None required this phase; flag for Phase 25 scoping.

---

_Reviewed: 2026-07-12T22:00:26Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
