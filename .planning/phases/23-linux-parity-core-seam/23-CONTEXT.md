# Phase 23: Linux Parity + Core Seam - Context

**Gathered:** 2026-07-12
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 23 delivers two things and nothing more:

1. **SBX-01 — Linux confinement parity proof.** A spike that determines whether a Linux `bwrap`+landlock profile can confine filesystem writes while preserving `claude` auth and API reachability, mirroring the passed macOS Seatbelt spike. A failed spike is a *recorded outcome* (documented gap + its consequence for phases 24–25), not a blocker.
2. **SBX-02 — the core seam.** `flowstate/sandbox.py` exposing `wrap(cmd, surface, project_root, env)` with per-platform profile builders and the default `observe` tier (env-scrub only, never blocks).

**Explicitly NOT in this phase:**
- Threading the seam into the 8 subprocess call sites (Phase 24).
- The `ProjectPreferences.sandbox` config field (Phase 24).
- Shipping the `confine` tier for real production use / the E2E denial proof (Phase 25).

Phase 23 is the foundation + the go/no-go on Linux; it builds the seam and the `observe` tier but does not wire them into callers or turn on confinement.

</domain>

<decisions>
## Implementation Decisions

### env-scrub policy (`observe` tier)
- **D-01: Denylist, not allowlist.** The `observe` tier strips known-secret patterns from the child environment (`*_API_KEY`, `*_TOKEN`, `*_SECRET`, `AWS_*`, `GITHUB_*`, and similar credential-shaped vars) and passes everything else through. Rationale: `observe` must *never* break a subprocess (that's its whole contract as the non-blocking default); an allowlist risks starving `repomix`/`npx`/`git` of environment they legitimately need. Accepted risk: a novel, non-pattern-matching secret var could slip through — acceptable for the `observe` tier, whose job is env hygiene, not hard confinement. (An allowlist may still be used inside `confine` later — that's a Phase-25 concern.)
- Reference sandflox `env.go` for the scrub pattern set, but reimplement natively.

### Linux confinement depth (SBX-01 spike + profile builder)
- **D-02: bwrap + landlock (defense-in-depth now).** The Linux tier layers landlock LSM path rules on top of the bwrap mount namespace, matching sandflox's `agent-sandbox-demos/agent-sbx` design — chosen over bwrap-only. **Consequence (load-bearing for the spike):** SBX-01 must prove that *both* the mount-namespace write confinement *and* the landlock path rules preserve `claude` auth/API reachability, not just bwrap alone. **Kernel constraint:** landlock needs Linux ≥ 5.13; on older kernels the profile builder must degrade (to bwrap-only, or to `observe` if bwrap is also unavailable) rather than hard-fail. Capture the kernel-version detection + degradation ladder as part of the spike findings.

### Linux spike-failure posture (SBX-01 outcome)
- **D-03: Asymmetric degrade.** If the Linux spike cannot preserve `claude` auth under bwrap+landlock, macOS `confine` still ships (the macOS mechanism is spike-proven), and Linux `confine` becomes a warned observe-only path ("kernel confinement pending") rather than blocking the whole tier. Honors SEED-003's "a failed spike is a valid outcome" and still ships the guardrail on the proven platform. This is the *contingency*; the goal remains full Linux parity.

### `wrap()` return contract (SBX-02 seam shape)
- **D-04: Return a transformed `(argv, env)` tuple.** `wrap(cmd, surface, project_root, env)` returns the (possibly sandbox-prefixed) argv and the scrubbed env; each future call site (Phase 24) becomes `cmd, env = wrap(cmd, surface, project_root, env)` followed by the existing `subprocess.run(cmd, env=env, ...)`. Chosen over a callable-that-executes or a context-manager because it's the smallest per-site diff (~2 lines), keeps each site's varied `subprocess.run` kwargs untouched, is trivially unit-testable (assert argv/env transform without spawning), and inverts no control flow.

### Claude's Discretion
- The exact denylist pattern set (D-01) — start from sandflox `env.go`, expand with obvious credential shapes; the researcher/planner finalizes the list.
- The internal module layout of `flowstate/sandbox.py` (platform-split functions à la sandflox's `exec_darwin.go`/`exec_other.go`, profile-builder helpers) — implementation detail.
- Whether `observe`-tier env-scrub is applied inside `wrap()` unconditionally or only when a tier is set — planner's call, but the Phase-23 default posture is `observe`.
- The precise landlock ruleset expression and the kernel-version detection method (D-02).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Milestone scope
- `.planning/seeds/SEED-003-sandbox-guardrail.md` — the milestone seed: locked decisions (native module, allow-default baseline, `observe` default, network paradox), the macOS spike result, the 8-site subprocess inventory, and the phase A/B/C shape this phase (23) implements.
- `.planning/REQUIREMENTS.md` — SBX-01, SBX-02 (this phase) + the full SBX-01..06 set and integrity rules.

### Reference implementation (sandflox — reference design, NOT a dependency)
- `/Users/jhogan/sandflox/env.go` — env-scrub reference for D-01 (denylist pattern set).
- `/Users/jhogan/sandflox/sbpl.go` — macOS SBPL profile generation (allow-default + selective-deny); the macOS profile builder mirrors this.
- `/Users/jhogan/sandflox/agent-sandbox-demos/agent-sbx` — Linux bwrap+landlock generalization; the reference for D-02's Linux tier.
- `/Users/jhogan/sandflox/exec_darwin.go`, `/Users/jhogan/sandflox/exec_other.go` — the platform-split exec pattern to mirror natively.

### Integration target (read to place the seam; DO NOT wire yet — that's Phase 24)
- `flowstate/bridge.py` around line 300–320 — where `env = {**os.environ}` is built and `CLAUDECODE` is popped just before `subprocess.run` at :308; the auth-load-bearing `llm` surface and the canonical env-scrub hook point.

### Prior-art memory (context, not a file the planner reads)
- Memory `flowstate-sandbox-spike` — the passed macOS spike detail: Keychain auth (not env), allow-default preserves auth, deny-default breaks it, the network paradox.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `flowstate/bridge.py:300` — the existing `env = {**os.environ}` + `env.pop("CLAUDECODE")` block is the exact model (and future call site) for env-scrub; the seam generalizes this per-surface.
- sandflox (`/Users/jhogan/sandflox`) — a complete, tested Go reference for every mechanism this phase needs (env-scrub, SBPL, bwrap+landlock, platform split); reimplement natively in Python, do not import or shell out.

### Established Patterns
- No existing platform detection in `flowstate/` (`sys.platform`/`platform.*` unused in source) — `flowstate/sandbox.py` introduces it cleanly; follow sandflox's `_darwin`/`_other` file-split convention.
- FlowState's "no new core runtime dependency" rule holds — the sandbox tiers shell out to OS binaries (`sandbox-exec`, `bwrap`) located PATH-style like `claude`/`repomix`, not via a Python package.
- Graceful-degradation-not-crash is the house style (repomix absent → degrade; `[semantic]` absent → warned no-op) — the `observe` default and the kernel-version degradation ladder (D-02) follow it.

### Integration Points
- Phase 23 builds the seam standalone; the 8 call sites it will eventually serve are `bridge.py:308`, `pack.py:115`, `distiller.py:92`, `tools/base.py:73`, `discipline.py:43/53/63/92`, `gsd_vendor.py:325/376` (wired in Phase 24, not here).

</code_context>

<specifics>
## Specific Ideas

- Match sandflox's mechanism choices deliberately (D-02 bwrap+landlock is a conscious "do the sandflox thing" call, not the simpler bwrap-only parity option) — sandflox is the maintainer's own proven design and the intended fidelity bar.
- The macOS baseline is `(allow default)` then selective `(deny file-write*)` re-allowing `$PROJECT`/`/private/tmp`/`/private/var/folders`/`/dev` + `(deny file-read* (subpath ~/.ssh))` — proven in the spike; the macOS profile builder should emit exactly this shape.

</specifics>

<deferred>
## Deferred Ideas

- **Threading `wrap()` into the 8 subprocess sites** — Phase 24 (SBX-03).
- **`ProjectPreferences.sandbox` config field** — Phase 24 (SBX-04).
- **The `confine` tier's real production profiles + E2E denial proof** (write-outside-root denied, `~/.ssh` read denied, auth survives) — Phase 25 (SBX-05).
- **Fail-loud on missing sandbox binary under `confine`** — Phase 25 (SBX-06).
- **Network egress allowlisting** — out of scope milestone-wide (the network paradox); tracked as SBX-F1.
- **Windows sandbox tier** — out of scope; SBX-F2.
- **Allowlist env-scrub inside `confine`** — possible Phase-25 refinement; `observe` uses the denylist (D-01).

</deferred>

---

*Phase: 23-Linux Parity + Core Seam*
*Context gathered: 2026-07-12*
