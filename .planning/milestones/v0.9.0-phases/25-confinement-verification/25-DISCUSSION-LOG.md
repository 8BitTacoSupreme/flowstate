# Phase 25: Confinement + Verification - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-12
**Phase:** 25-Confinement + Verification
**Areas discussed:** SBX-06 fail-loud reconciliation, WR-03 confine HOME, SBX-05 E2E scope, WR-2 npm token

---

## SBX-06 fail-loud vs RUNG-3 degrade

| Option | Description | Selected |
|--------|-------------|----------|
| Fail loud when confine can't confine | confine + no binary → raise with install hint; partial capability still degrades within confinement; observe untouched | ✓ |
| Degrade to observe with warning | Keep RUNG-3 everywhere; never hard-fail | |
| Fail loud macOS, degrade Linux | Platform-asymmetric | |

**User's choice:** Fail loud when confine can't confine (D-01)
**Notes:** SBX-06 literal. Replaces Phase-23 RUNG-3 observe-degrade for the explicit-confine case. Linux bwrap+landlock→bwrap-only partial degrade still allowed (still confinement). Default observe stays non-blocking. Confine tier may now raise — module "never raises" wording scoped to observe + probes.

---

## WR-03 confine HOME / credential

| Option | Description | Selected |
|--------|-------------|----------|
| Bind a minimal writable HOME/cache | Add bound-writable scratch to build_linux_bwrap_args; re-probe with file credential | |
| Verify first, then decide | Re-probe with the exact shipped read-only-HOME argv + file credential FIRST; add writable HOME only if it fails | ✓ |

**User's choice:** Verify first (D-02)
**Notes:** Empirical — no speculative profile loosening. Re-probe uses the production file credential (~/.claude/.credentials.json) + exact shipped argv, not the writable-HOME/token shortcut the Phase-23 spike used.

---

## SBX-05 E2E denial proof scope

| Option | Description | Selected |
|--------|-------------|----------|
| macOS real test + Linux Docker verification | macOS skip-if-not-darwin pytest (native sandbox-exec) + Linux denial E2E via committed Docker artifact | ✓ |
| macOS real test only | CI macOS proof; Linux by Phase-23 spike + golden tests | |

**User's choice:** macOS real + Linux Docker verification (D-03)
**Notes:** Shares the Docker + real-credential harness with the D-02 WR-03 re-probe — plan as one Linux verification step.

---

## WR-2 npm *_TOKEN scrub

| Option | Description | Selected |
|--------|-------------|----------|
| Document as known limitation | Record in docs + comment; don't widen exemption | ✓ |
| Add tool-surface auth exemption | Pass NPM_TOKEN/GITHUB_TOKEN for the tool surface | |
| Leave gsd_vendor npm unscrubbed | Skip scrub at that one site | |

**User's choice:** Document as known limitation (D-04)
**Notes:** Not FlowState's path (public npm). Widening the exemption weakens the core secret-stripping guarantee. Revisit only if a private-registry user appears.

---

## Claude's Discretion

- Temp .sb profile cleanup (WR-09): call-site try/finally unlinking argv[2] (keep the locked tuple contract; no spawn helper unless unworkable). Bridge is the primary confine target.
- Fail-loud exception type/name + per-platform install-hint wording.
- Fail-loud check reuses check_bwrap_available() (functional) vs a lighter presence check — functional preferred (AppArmor caveat).

## Deferred Ideas

- Per-surface network/profile policy; widening the scrub exemption; Windows tier / network egress; a sandbox.run() spawn helper; CLI/interview surface for the sandbox field.
