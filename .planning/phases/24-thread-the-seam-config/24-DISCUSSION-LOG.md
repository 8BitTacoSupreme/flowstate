# Phase 24: Thread the Seam + Config - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-12
**Phase:** 24-Thread the Seam + Config
**Areas discussed:** site coverage, surface taxonomy, config field shape, default posture

---

## SBX-03 site coverage

| Option | Description | Selected |
|--------|-------------|----------|
| Agent-directed only | Wrap bridge/distiller/tools-base/pack/gsd_vendor; leave discipline.py git-reads bare | ✓ |
| All 8 sites uniformly | Route every subprocess through wrap() | |
| LLM sites only | Wrap only bridge/distiller (claude) | |

**User's choice:** Agent-directed only (D-01)
**Notes:** Wrap where agent/untrusted content flows; leave internal read-only git commands bare (no injection surface, confining `git status` buys nothing). Deliberate commented exclusion, not a silent omission.

---

## Surface taxonomy

| Option | Description | Selected |
|--------|-------------|----------|
| Descriptive names, policy in P25 | `llm`/`tool`/`vcs` strings now; confine policy keys off them in Phase 25 | ✓ |
| Surface carries policy now | Attach network/profile policy per surface in Phase 24 | |

**User's choice:** Descriptive names, policy deferred (D-02)
**Notes:** Keeps Phase 24 about wiring; observe ignores surface (as wrap() already does).

---

## Config field shape

| Option | Description | Selected |
|--------|-------------|----------|
| Single global enum | `sandbox: str = "observe"` (observe/confine), one global level | ✓ |
| Per-surface levels | `sandbox: dict` mapping surface→level | |

**User's choice:** Single global enum (D-03)
**Notes:** Defaulted field, no migration, simplest. Per-surface granularity deferred until needed.

---

## Default posture

| Option | Description | Selected |
|--------|-------------|----------|
| Default observe / scrub live | Default `observe`; env-scrub live by default on every wrapped site | ✓ |
| Default off / byte-identical | Sandbox fully opt-in; zero behavior change | |

**User's choice:** Default observe / scrub live (D-04)
**Notes:** Per SBX-04's wording. Real runtime change (secret-shaped vars stripped) but conservative denylist + `_AUTH_EXEMPT` protects claude; plan must confirm no wrapped subprocess regresses.

---

## Claude's Discretion

- Threading the level into non-bridge sites (pack/distiller/tools-base/gsd_vendor) — mirror `_make_bridge`'s pattern.
- Preserving bridge.py's env-prep ordering (CLAUDECODE pop + 1h-cache var) before/after the scrub.

## Deferred Ideas

- confine production profiles + E2E denial proof, fail-loud on missing binary → Phase 25.
- WR-03 production-shape confirmations (writable HOME, file-path credential) → Phase 25.
- Per-surface policy / config dict, wrapping the git-reads → deferred.
