---
id: SEED-003
status: planted
planted: 2026-07-11
planted_during: v0.8.0 Harness Tax & Value (Phase 22 paused, verdict run owed)
proposed_as: v0.9.0 "Sandbox Guardrail"
trigger_when: v0.9.0 kickoff — independent of the owed Phase-22 verdict run (touches bridge.py/state.py/new sandbox.py, not bench/)
scope: ~3 phases, minor bump
spike: macOS PASSED 2026-07-11 (ad-hoc, not yet in repo); Linux bwrap parity UNPROVEN
gates: []
---

# SEED-003: v0.9.0 "Sandbox Guardrail" — OS-level blast-radius reduction on every subprocess

Proposed milestone (minor bump after v0.8.0). FlowState shells out to `claude --print`,
`repomix`, `npx`, and `git` across the codebase with `env={**os.environ}` and no filesystem
confinement. This seed adds an **OS-sandboxing guardrail** — a native Python seam that wraps
each subprocess in a kernel sandbox (macOS Seatbelt / Linux bwrap+landlock) plus an env-scrub
tier — so a misbehaving or prompt-injected agent call can't write outside the project root or
read arbitrary secrets. Modeled on the maintainer's own **sandflox**
(`/Users/jhogan/sandflox`) as a *reference design, not a runtime dependency*.

## Why This Matters

Every subprocess FlowState spawns inherits the full user environment and unrestricted
filesystem/network access. The primary risk surface is `bridge.py:308` — the `claude --print`
call that runs LLM-directed work with `capture_output` but zero confinement. A prompt-injected
research or strategy step could exfiltrate `~/.ssh`, tamper with files outside the project, or
leak env secrets. There is currently **no boundary** between "the pipeline" and "the machine."

The guardrail is a **blast-radius reducer, not an egress firewall** (see the network paradox
below). Default posture is non-blocking (`observe`) so it can ship without breaking any
existing run, then tighten opt-in.

## Spike Result — macOS PASSED (2026-07-11, ad-hoc; not yet in repo)

A throwaway spike in the session scratchpad proved the load-bearing macOS mechanism:

- **`claude` on this machine auths via the macOS Keychain** (`security` service
  `"Claude Code-credentials"`, acct `jhogan`) — `ANTHROPIC_API_KEY` is **UNSET** and there is
  no `~/.claude/.credentials.json`. So the sandbox's job is **preserving Keychain /
  `SecurityServer` mach reachability**, not passing an env key. Env-scrub is pure upside.
- An **allow-default + selective-deny** SBPL profile (`(allow default)` then `(deny file-write*)`
  re-allowing `$PROJECT` / `/private/tmp` / `/private/var/folders` / `/dev`, plus
  `(deny file-read* (subpath ~/.ssh))`) run via
  `sandbox-exec -f prof.sb -D PROJECT=… -- claude --print` returned **exit 0 + real model
  output** → API reachable and Keychain auth survives. Write inside `$PROJECT` OK; write to
  `$HOME` denied; `~/.ssh` read denied. No `sandbox-exec` deprecation stderr noise.
- **Load-bearing consequence:** a **deny-default** profile (agent-sbx's macOS variant) would
  break Keychain auth. **Allow-default + selective-deny is the correct baseline for FlowState.**

**Still unproven:** Linux `bwrap` parity (spike ran darwin/arm64 only). This is the primary
open risk the milestone's first phase must retire before committing to the cross-platform tier.

## The Network Paradox (accepted constraint)

`sandbox-exec` and `bwrap` are **all-or-nothing on network** — no per-host filtering. Any
surface that spawns `claude` (or `repomix`/`npx` fetching) must run **net-ALLOWED**, so the
guardrail cannot be an egress firewall. It confines **filesystem + environment**, reducing
blast radius; egress control is explicitly out of scope.

## Locked Decisions (from the spike + `how-might-we-incorporate-mighty-mist.md`, now superseded/parked)

- **Native `flowstate/sandbox.py`** — sandflox (`env.go` env-scrub, `sbpl.go` macOS SBPL,
  `agent-sandbox-demos/agent-sbx` Linux bwrap+landlock) is the **reference**, not imported.
  No new runtime dependency.
- **Single `wrap(cmd, surface, project_root, env)` seam** threaded through the subprocess
  sites. Reality check on disk: there are **8** `subprocess.run` sites, not the 6 the spike
  note estimated — `bridge.py:308` (the auth-load-bearing `claude` call), `pack.py:115`,
  `distiller.py:92`, `tools/base.py:73`, `discipline.py` ×4 (git reads), `gsd_vendor.py` ×2
  (npm/parity). Phase planning decides which are wrapped vs left bare (the discipline git-reads
  and gsd_vendor npm calls are internal, not LLM-directed — candidate to skip in tier 1).
- **Cover all agent-directed surfaces**, tiered kernel confinement on **macOS + Linux**.
- **Default profile `observe`** — env-scrub only, never blocks — so it ships non-breaking; the
  confining SBPL/bwrap profile is opt-in via config.
- **Config on `ProjectPreferences`** (`flowstate/state.py:38`) as a defaulted field → **no
  state migration** required (backward-compatible load).
- **Spike-first, then milestone** — macOS spike done; Linux spike is the milestone's gating
  first step.

## Scope Estimate

**~3 phases, minor bump (v0.9.0).** Rough shape (refine at plan time):

- **Phase A — Linux parity spike + `sandbox.py` core.** Retire the bwrap+landlock unknown on
  Linux (mirror the macOS allow-default finding); build `flowstate/sandbox.py` with the
  `wrap(cmd, surface, project_root, env)` seam, the `observe` env-scrub tier, and per-platform
  profile builders. Unit-tested against a fake command; profile emission golden-tested.
- **Phase B — Thread the seam + config.** Route the agent-directed subprocess sites through
  `wrap()`; add the `ProjectPreferences` sandbox field (defaulted, no migration) with
  `observe` / `confine` levels; env-scrub live by default, confinement opt-in. Preserve
  Keychain/API reachability on every wrapped call.
- **Phase C — Confinement profiles + verification.** Ship the allow-default+selective-deny
  macOS profile and the bwrap Linux equivalent behind `confine`; end-to-end test that a real
  `claude --print` succeeds confined (auth survives) while a write outside `project_root` and a
  read of `~/.ssh` are denied. Fail-loud if the platform sandbox binary is missing.

## Boundary / Non-Goals

- **Not an egress firewall** (network paradox above) — filesystem + env confinement only.
- **Not a sandflox dependency** — reference design reimplemented natively in Python.
- **Not a Windows tier** — macOS + Linux only (Windows has no equivalent primitive here).
- Does **not** gate or touch the v0.8.0 bench/verdict work — fully independent track.

## Breadcrumbs

- Reference implementation: `/Users/jhogan/sandflox` — `env.go` (env-scrub), `sbpl.go` (macOS
  SBPL), `agent-sandbox-demos/agent-sbx` (Linux bwrap+landlock generalization).
- Primary integration chokepoint: `flowstate/bridge.py:308` (`subprocess.run`,
  `env={**os.environ}`, `CLAUDECODE` popped just above at :301).
- Config attach point: `flowstate/state.py:38` (`ProjectPreferences`, defaulted field).
- Full subprocess inventory: `bridge.py:308`, `pack.py:115`, `distiller.py:92`,
  `tools/base.py:73`, `discipline.py:43/53/63/92`, `gsd_vendor.py:325/376`.
- Spike facts + decisions preserved in memory `flowstate-sandbox-spike.md`.

## Notes

Captured 2026-07-11 while v0.8.0 Phase 22 (The Verdict) is paused with an owed 5×3 real
benchmark run. This milestone is sequenced to start **in parallel** with that owed run — it
shares no files with `bench/`. The macOS spike is real and passed; the honest open risk is
Linux bwrap parity, which Phase A must prove before the cross-platform promise is committed.
