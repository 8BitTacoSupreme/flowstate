# Phase 23: Linux Parity + Core Seam - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-12
**Phase:** 23-Linux Parity + Core Seam
**Areas discussed:** env-scrub policy, Linux confinement depth, Linux spike-failure posture, wrap() return contract

---

## env-scrub policy (`observe` tier)

| Option | Description | Selected |
|--------|-------------|----------|
| Denylist | Strip known-secret patterns (*_API_KEY/*_TOKEN/*_SECRET/AWS_*/GITHUB_*), pass the rest; never breaks a subprocess | ✓ |
| Hybrid by surface | Tight allowlist for `llm`, denylist for tool surfaces | |
| Allowlist | Pass only PATH/HOME/LANG/TERM + keychain-needed; risks starving repomix/npx/git | |

**User's choice:** Denylist (D-01)
**Notes:** `observe` must never block a subprocess — the denylist is the non-breaking default. Allowlist reserved as a possible `confine`-tier refinement. Accepted risk: a novel non-pattern secret var could slip through.

---

## Linux confinement depth

| Option | Description | Selected |
|--------|-------------|----------|
| bwrap-only | Mount-namespace write confinement; parity with macOS single mechanism; more kernels; simpler spike | |
| bwrap + landlock | Add landlock LSM path rules (sandflox agent-sbx parity); defense-in-depth; needs kernel 5.13+ | ✓ |

**User's choice:** bwrap + landlock (D-02) — overrode the bwrap-only recommendation
**Notes:** Deliberate "do the sandflox thing" call for defense-in-depth now. Consequence: SBX-01 spike must prove BOTH mount-namespace AND landlock preserve claude auth; kernel ≥5.13 becomes a documented constraint with a degradation ladder (bwrap-only → observe) on older kernels.

---

## Linux spike-failure posture

| Option | Description | Selected |
|--------|-------------|----------|
| Asymmetric degrade | macOS `confine` ships; Linux `confine` → warned observe-only on failure | ✓ |
| Best-effort Linux confine | Ship Linux confine with an auth workaround (loosened bind / --share-net) | |
| Block confine on both | Withhold macOS confine too until Linux parity | |

**User's choice:** Asymmetric degrade (D-03)
**Notes:** Honors SEED-003's "failed spike is a valid outcome"; ships the proven macOS guardrail regardless. Full Linux parity remains the goal — this is the contingency.

---

## wrap() return contract

| Option | Description | Selected |
|--------|-------------|----------|
| (argv, env) tuple | `cmd, env = wrap(...)` then existing subprocess.run; ~2-line diff/site | ✓ |
| Callable that executes | wrap() runs the subprocess; most encapsulated, bigger refactor | |
| Context manager | `with wrap(...) as run:`; heavier ceremony for an argv/env transform | |

**User's choice:** (argv, env) tuple (D-04)
**Notes:** Smallest per-site diff across the 8 subprocess sites, keeps each site's varied subprocess.run kwargs untouched, trivially unit-testable, no control-flow inversion.

---

## Claude's Discretion

- Exact denylist pattern set (start from sandflox `env.go`).
- Internal module layout of `flowstate/sandbox.py` (platform-split helpers).
- Landlock ruleset expression + kernel-version detection method.
- Whether env-scrub applies unconditionally in `wrap()` or only when a tier is set.

## Deferred Ideas

- Threading `wrap()` into the 8 subprocess sites → Phase 24.
- `ProjectPreferences.sandbox` config field → Phase 24.
- `confine` production profiles + E2E denial proof → Phase 25.
- Fail-loud on missing sandbox binary → Phase 25.
- Network egress allowlisting (SBX-F1) / Windows tier (SBX-F2) → out of scope.
