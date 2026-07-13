# Phase 25: Confinement + Verification - Context

**Gathered:** 2026-07-12
**Status:** Ready for planning

<domain>
## Phase Boundary

The LAST v0.9.0 phase. Makes the `confine` tier real, verified, and honest — everything the guardrail needs to be trusted in production.

1. **SBX-05 — confine ships + is E2E-proven.** The `confine` tier (macOS SBPL + Linux bwrap+landlock profiles, already built + golden-tested in Phase 23) is wired for real production use (including temp-profile lifecycle), and an end-to-end test proves a real `claude --print` succeeds confined (auth survives, API reachable) while a write outside `project_root` and a read of `~/.ssh` are DENIED.
2. **SBX-06 — fail loud on a missing binary.** Under `confine`, when no confinement is achievable, the guardrail raises with an install hint — it never silently runs a command unconfined.

Also folds in the two carried debts: **WR-03** (the Linux confine argv leaves HOME read-only + only token-path auth was proven) and **WR-2** (observe strips `*_TOKEN`).

**Explicitly NOT in this phase:** no new surfaces/sites (Phase 24 wired them); no per-surface network policy; no Windows tier; no network egress control (the network paradox is milestone-wide out of scope).

</domain>

<decisions>
## Implementation Decisions

### SBX-06 — fail loud vs the Phase-23 RUNG-3 degrade
- **D-01: Fail loud when `confine` is requested and NO confinement is achievable.** If `sandbox=confine` and the platform's sandbox binary is genuinely absent (`sandbox-exec` on macOS, `bwrap` on Linux) — or the platform is unsupported (not darwin/linux) — `wrap()` (or the confine dispatch) RAISES a clear error with an install hint. It NEVER silently runs the command unconfined. This **replaces** Phase-23's RUNG-3 "bwrap unavailable → observe fallback" and the silent `_find_sandbox_exec` `/usr/bin/...` fallback FOR THE EXPLICIT-CONFINE case.
  - **Partial capability still degrades WITHIN confinement:** Linux "bwrap present, landlock unavailable" still steps RUNG-1 → RUNG-2 (bwrap-only) — that's still confinement, so no fail-loud. Only "no confinement at all" fails loud.
  - **Default `observe` is untouched** — it stays non-blocking and never raises (the observe path already returns `(cmd, _scrub_env(env))` before any platform dispatch).
  - **Contract change to record:** the confine tier can now raise (a new `SandboxUnavailableError` or similar); the module docstring's "never raises" wording must be scoped to the observe tier + the availability *probes*, not the confine dispatch. Note this is clean given Linux parity PROVED in Phase 23 (D-03's asymmetric-degrade contingency never had to fire).

### WR-03 — writable surface under Linux confine (verify-first)
- **D-02: Verify first, then decide the surface.** Re-run the confined `claude --print` probe with the EXACT shipped `build_linux_bwrap_args` argv (read-only HOME under `--ro-bind / /`) AND the FILE-based credential (`~/.claude/.credentials.json`, 0600 — the production default `bridge.py` uses), NOT the writable-HOME + token-path shortcut the Phase-23 spike used. ONLY if confined claude actually fails for a filesystem-write reason do we add a minimal bound-writable HOME/cache dir to `build_linux_bwrap_args` (mirroring the macOS profile already re-allowing `/private/var/folders` temp writes). Empirical — no speculative loosening of the profile. Record the probe outcome (works as-is, or needed a writable HOME) in the phase's verification artifact.

### SBX-05 — E2E denial proof scope
- **D-03: macOS real test + Linux Docker verification.** macOS: a real `skip-if-not-darwin` pytest that runs `sandbox-exec` natively and asserts confined `claude`/a shell succeeds while a write outside `project_root` and a read of `~/.ssh` are denied — CI-runnable on macOS. Linux: the confined-denial E2E runs via the Phase-23 Docker recipe as a COMMITTED verification artifact (privileged Docker isn't CI-friendly), mirroring how the SBX-01 spike (`23-SPIKE-LINUX.md`) was recorded. "E2E-proven" = real on both platforms, CI-gated where feasible.
  - The D-02 WR-03 re-probe and this D-03 Linux denial E2E SHARE the Docker + real-credential harness — plan them as one Linux verification step, not two.

### WR-2 — npm `*_TOKEN` scrub
- **D-04: Document as known limitation, do NOT widen the exemption.** `gsd_vendor`'s npm runs at `observe`, whose denylist strips `*_TOKEN` (incl. `NPM_TOKEN`). This is not FlowState's path (public `get-shit-done-cc` from public npm). Record it in the sandbox docs + a code comment near the gsd_vendor wrap site; do NOT add `NPM_TOKEN`/tool-auth vars to an exempt set — that would widen what secret-shaped vars survive the scrub and weaken the guardrail's core guarantee. Revisit only if a real private-registry user appears.

### Human-gated credential step (like 23-04)
- Both D-02 (WR-03 re-probe) and D-03 (Linux denial E2E) need a real confined `claude` run inside a Linux container with a working credential. This is a `checkpoint:human-action` (mint/provide a credential) mirroring Phase 23's 23-04. Prefer the FILE-based `~/.claude/.credentials.json` path (the WR-03 concern) as the primary proof; a token is the fallback. NEVER write the credential value into any committed artifact.

### Claude's Discretion
- **Temp `.sb` profile cleanup (WR-09):** `_wrap_macos` writes a temp `.sb` file the caller must unlink after the child exits (leak otherwise). Given the D-04 `(argv, env)` tuple contract is LOCKED (Phase 23), cleanup lives at the confine-capable call site(s) — a `try/finally` around the `subprocess.run` that unlinks `argv[2]` when the returned argv is a macOS `sandbox-exec -f <path>` shape. Do NOT introduce a second seam shape (a spawn helper) unless the planner finds the call-site cleanup genuinely unworkable. The bridge is the primary confine target; wire cleanup there.
- The exact exception type/name for the fail-loud (D-01) and its message wording (install hint per platform).
- Whether the fail-loud check reuses `check_bwrap_available()` (functional smoke test) or a lighter presence check for the raise decision — but a functional check is preferred (Ubuntu 24.04 AppArmor blocks bwrap even when the binary exists).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### This phase
- `.planning/phases/25-confinement-verification/25-CONTEXT.md` — this file (D-01..D-04 + the human-gated credential note).
- `.planning/REQUIREMENTS.md` — SBX-05, SBX-06 + integrity rules.

### The confine path being finished (all already exist — do NOT rebuild, wire + verify + harden)
- `flowstate/sandbox.py` — `wrap()` confine dispatch (`:164-170`), `_wrap_macos` (`:470`, incl. the WR-09 temp-profile leak note), `_wrap_linux` (`:499`, the RUNG-3 observe-fallback at `:531-540` that D-01 tightens), `build_macos_profile`, `build_linux_bwrap_args`, `_find_sandbox_exec` (`:451`, the silent `/usr/bin` fallback D-01 tightens), `check_bwrap_available` (`:428`).
- `flowstate/bridge.py:309` — the primary `confine` target (`wrap(cmd, "llm", ..., tier=self.config.sandbox)`); temp-profile cleanup (WR-09) wires here.

### Carried debts (read the caveats)
- `.planning/phases/23-linux-parity-core-seam/23-SPIKE-LINUX.md` — the PARITY-PROVEN verdict + the WR-03 caveat (writable HOME + token-path divergence) this phase closes.
- `.planning/phases/24-thread-the-seam-config/24-REVIEW.md` — the WR-2 (npm NPM_TOKEN) finding this phase documents.

### Prior decisions (context)
- `.planning/phases/23-linux-parity-core-seam/23-CONTEXT.md` — D-01..D-04 (the seam's design, incl. D-03 asymmetric-degrade this phase reconciles with SBX-06).
- Memory `flowstate-v09-sandbox-opened` — the milestone's running state + the two carried items.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- The entire confine mechanism is BUILT (Phase 23): profile builders, platform dispatch, Landlock ctypes, functional bwrap probe. Phase 25 wires the live spawn, tightens the fail-loud, closes WR-03, and verifies — it does NOT build new confinement machinery.
- The Phase-23 Docker recipe (`23-SPIKE-LINUX.md` + the scratchpad landlock scripts) is the harness for the D-02/D-03 Linux verification — reuse it.
- `_find_sandbox_exec`/`_find_bwrap` already follow the `pack.py:_find_repomix` locator pattern — the fail-loud gate hooks onto their "not found" result.

### Established Patterns
- Graceful-degradation-never-crash is the house style — SBX-06 (D-01) is the deliberate EXCEPTION for the explicit-confine case, and must be a clearly-documented, narrowly-scoped raise (confine-only; observe still degrades).
- The macOS confine E2E can run natively (sandbox-exec is present on darwin) as a `skip-if-not-darwin` pytest; the Linux E2E follows the committed-verification-artifact pattern from the Phase-23 spike (privileged Docker off-CI).

### Integration Points
- `wrap()`'s confine dispatch (`:164-170`) is where the fail-loud raise (D-01) lands, or a helper it calls. The bridge (`bridge.py:309`) is where the live confined spawn + temp-profile cleanup (WR-09) wire.

</code_context>

<specifics>
## Specific Ideas

- The macOS confine baseline is the spike-proven `(allow default)` + selective `(deny file-write*)` re-allowing `$PROJECT`/`/private/tmp`/`/private/var/folders`/`/dev` + `(deny file-read* (subpath ~/.ssh))` — the SBX-05 macOS E2E asserts exactly this: confined write to `$PROJECT` OK, write to `$HOME` denied, read `~/.ssh` denied, `claude` auth (Keychain) survives.
- The WR-03 re-probe's whole point is fidelity to production: the EXACT shipped `build_linux_bwrap_args` argv + the FILE credential `bridge.py` really uses — not the writable-HOME/token shortcut. If it passes as-is, the confine profile ships unchanged; if it fails, add the minimal writable HOME and re-verify.

</specifics>

<deferred>
## Deferred Ideas

- **Per-surface network/profile policy** (`surface` carrying `confine` policy per `llm`/`tool`/`vcs`) — still deferred; `confine` applies one global profile shape.
- **Widening the scrub exemption for tool-auth vars** (NPM_TOKEN/GITHUB_TOKEN) — deferred (D-04 documents WR-2, doesn't fix it).
- **Windows confine tier / network egress allowlisting** — out of scope milestone-wide (SBX-F1/F2).
- **A `sandbox.run()` spawn helper** — only if call-site temp-profile cleanup proves unworkable (Claude's Discretion); default is to keep the locked `(argv, env)` tuple contract.
- **CLI/interview surface for `ProjectPreferences.sandbox`** (Phase-24 Info item) — a UX follow-up, not required for the confine tier to work; revisit post-milestone.

</deferred>

---

*Phase: 25-Confinement + Verification*
*Context gathered: 2026-07-12*
