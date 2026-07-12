# Requirements: v0.9.0 Sandbox Guardrail

**Goal:** Put an OS-level blast-radius boundary between FlowState's subprocess calls and the machine. FlowState shells out to `claude --print`, `repomix`, `npx`, and `git` with `env={**os.environ}` and no filesystem confinement; a prompt-injected agent call can currently write outside the project root or read arbitrary secrets. Add a native `flowstate/sandbox.py` seam (macOS Seatbelt / Linux bwrap+landlock + an env-scrub tier) that confines each agent-directed subprocess. Source: [`seeds/SEED-003-sandbox-guardrail.md`](./seeds/SEED-003-sandbox-guardrail.md). Modeled on the maintainer's own **sandflox** as a reference design, not a runtime dependency.

**Integrity rules (milestone-wide):** the guardrail is a **blast-radius reducer, not an egress firewall** (`sandbox-exec`/`bwrap` are all-or-nothing on network — no per-host filtering; claude-spawning surfaces run net-ALLOWED). Default posture is **non-blocking** (`observe` = env-scrub only) so it ships without breaking a single existing run; confinement is opt-in. **Auth must survive confinement** — `claude` on this machine auths via the macOS Keychain, so an allow-default+selective-deny profile is the load-bearing baseline (a deny-default profile breaks auth). The macOS mechanism is spike-proven; **Linux bwrap parity is the milestone's gating unknown** (SBX-01) — a failed spike is a valid outcome that reshapes later phases, not a blocker to hide.

## v0.9.0 Requirements

### Sandbox Core (Linux parity + the seam)

- [ ] **SBX-01**: a Linux `bwrap`+landlock spike proves an allow-default + selective-deny profile preserves `claude` auth and API reachability (mirroring the passed macOS Seatbelt spike), or honestly documents the parity gap and its consequence for later phases. A failed spike is a recorded outcome, not a silent skip.
- [ ] **SBX-02**: `flowstate/sandbox.py` exposes a single `wrap(cmd, surface, project_root, env)` seam with per-platform profile builders; the default `observe` tier is **env-scrub only and never blocks** a command. Unit-tested against a fake command; profile emission golden-tested.

### Thread the Seam + Config

- [ ] **SBX-03**: the agent-directed subprocess sites are routed through `wrap()` (at minimum `bridge.py:308`, the auth-load-bearing `claude --print` call), and Keychain/API reachability is preserved on every wrapped call. Internal git-read (`discipline.py`) and npm (`gsd_vendor.py`) sites are wrapped or left bare per an explicit plan-time decision.
- [ ] **SBX-04**: `ProjectPreferences` (`flowstate/state.py`) gains a defaulted `sandbox` level field (`observe` / `confine`); load stays backward-compatible with **no state migration** (defaulted field), and the default is `observe`.

### Confinement + Verification

- [ ] **SBX-05**: the `confine` tier ships the allow-default + selective-deny **macOS SBPL** profile and the **Linux bwrap** equivalent; an end-to-end test confirms a real `claude --print` succeeds confined (auth survives, API reachable) while a write outside `project_root` and a read of `~/.ssh` are **denied**.
- [ ] **SBX-06**: under `confine`, a missing platform sandbox binary (`sandbox-exec` / `bwrap`) **fails loud** with an install hint — the guardrail never silently runs a command unconfined when confinement was requested.

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| SBX-01 | Phase 23 | Pending |
| SBX-02 | Phase 23 | Pending |
| SBX-03 | Phase 24 | Pending |
| SBX-04 | Phase 24 | Pending |
| SBX-05 | Phase 25 | Pending |
| SBX-06 | Phase 25 | Pending |

## Future Requirements (deferred)

- **SBX-F1 — network egress allowlisting**: per-host filtering is impossible with `sandbox-exec`/`bwrap` alone; revisit only if a userspace proxy (e.g. an mitm egress gateway) is justified.
- **SBX-F2 — Windows tier**: no equivalent kernel primitive; deferred until a Windows user asks.

## Out of Scope

- **Egress firewall / network confinement** — the network paradox: kernel sandboxes are all-or-nothing on network, and every `claude`-spawning surface needs the network, so this milestone confines filesystem + environment only.
- **sandflox as a runtime dependency** — sandflox (`env.go`/`sbpl.go`/`agent-sbx`) is the reference design, reimplemented natively in Python; FlowState does not shell out to or import it.
- **Windows sandbox tier** — macOS + Linux only.
- **Blocking-by-default confinement** — `observe` (env-scrub, non-blocking) is the default so the guardrail ships without regressing any existing run; `confine` is opt-in.

---

# Carried: v0.8.0 Harness Tax & Value — VERDICT RUN OWED

> **Status:** v0.8.0 is the ledger-active milestone; phases 19–21 shipped and are Validated. **Phase 22 (The Verdict) is paused** — the code (driver, pre-registration, grounding fix) shipped, but the paired-design **5×3 real benchmark run (~5–7 hr, paid) on floxybot2 has not been executed**. VERD-01..03 are marked `[x]` below optimistically; the run + recorded verdict is the outstanding debt. v0.9.0 was scoped in parallel (SEED-003) because it shares no files with `bench/`. Do not archive v0.8.0 until the verdict run completes.

**Goal:** Now that the eval harness is trustworthy (v0.6.2), answer the question v0.7.0 deliberately doesn't — **does FlowState's context stack improve output quality enough to justify its token and latency cost?** Measure the tax, decouple the evaluator, activate the dormant wiki layer in production, then run a pre-registered paired-design verdict on a real repo. Source: [`seeds/SEED-001-harness-tax-and-value.md`](./seeds/SEED-001-harness-tax-and-value.md). The bench-side halves shipped in v0.6.2; this milestone is the production + measurement-science half.

**Integrity rules (milestone-wide):** never let the LLM judge become the load-bearing metric (`metrics.py` stays authoritative, judge excluded from `compounding_score`); judge-model ≠ producer-model enforced in code, not convention; verdict rules pre-registered before the run; report the tax even when it's embarrassing; a null result is a result.

## v0.8.0 Requirements

### The Tax (token/cost/latency accounting)

- [x] **TAX-01**: `ClaudeBridge.run()` captures real usage — `BridgeResult` gains a `usage` field populated via the existing `output_format="json"` path, while `.output` stays byte-identical (no caller regression). Deterministic, no new LLM calls.
- [x] **TAX-02**: `RunSnapshot` records real `tokens_in` / `tokens_out` / `cache_read` + `wall_clock_s` per run (replacing the `len(prefix)//4` `prefix_tokens` estimate as the source of truth for consumption).
- [x] **TAX-03**: `bench/report.py` reports per-arm tokens and seconds alongside the existing quality metrics (Track-2, excluded from `compounding_score`).
- [x] **TAX-04**: cost-per-success uses `flowstate verify`'s deterministic acceptance gates as the denominator (not "commits"); the denominator is named honestly in the report.

### Evaluator Independence

- [x] **IND-01**: `bench/judge.py` fails loud when `--judge-model` is absent or equals the producer model — no silent same-model grading.
- [x] **IND-02**: multi-judge averaging in `judge.py` (majority vote + Wilson CI), mirroring the pattern already in `bench/grounding.py` (`--judge-models`).
- [x] **IND-03**: a test asserts `bench/metrics.py` stays the authoritative deterministic scorer and the LLM judge remains excluded from `compounding_score` under the new multi-judge path.

### Activate the Wiki (production wiring of the dormant WIKI-F1 layer)

- [x] **WIKI-03**: a production caller runs the memory→wiki distiller (promoted from `bench/distiller.py`) to write the `.planning/codebase/wiki/` article corpus, manifest-tracked and staleness-gated like `flowstate pack` (regenerates only when memory changed); runs end-of-run so the next run reads this run's distilled knowledge.
- [x] **WIKI-04**: an opt-in config flag makes the orchestrator pass `include_layers={"wiki"}` to `build_context_prefix()`, so the Phase-11 semantic wiki layer fires in production; the default (flag off) stays byte-identical, and the path degrades gracefully when the `[semantic]` extra is absent.
- [x] **WIKI-05**: the `flowstate[semantic]` extra is surfaced as the requirement for the KNN wiki path; with the flag on but the extra absent, the layer is a no-op-with-warning (never a hard crash).
- [x] **WIKI-06**: a dogfood smoke-test runs FlowState's own pipeline on a FlowState task with the wiki flag on, using this project's `memory.db`, and asserts the wiki layer demonstrably fires (corpus globbed, top-k injected) with the run green — phase acceptance is "the layer fires," NOT "quality improved."

### The Verdict

- [x] **VERD-01**: verdict rules (effect-size threshold, CI width, minimum n, what counts as a win) are pre-registered in writing **before** the paired-design run.
- [x] **VERD-02**: a paired-design run via `bench/close_loop.py` on a **real repo** (not `bench/fixtures/sample_project`) across arms `none` · `pack` · `memory` · `wiki` · `full`, measuring the **compounding curve** (run 1 empty → wiki value appears run 2+), not a one-shot.
- [x] **VERD-03**: the verdict reports quality **and** tax per arm and applies the pre-registered rules; a null `wiki − none` (or any arm) is an accepted, documented outcome that licenses stripping the layer.

## Future Requirements (deferred)

- **RERANK-F1 / RERANK-F2**: production reranker wiring (from v0.7.0 backlog) — only if the bench shows the embeddings, not merely the reranker, carry the win.
- **RET-F1..F3 / QA-F1..F4**: v0.7.0 retrieval/QA-track future requirements — see `.planning/deferred/v0.7.0-REQUIREMENTS.md`.
- **Auto-distill at end of every run** (vs explicit `flowstate distill`) — WIKI-03 ships explicit-first; auto-once-proven is a follow-up once the verdict justifies the invisible loop.

## Out of Scope

- **v0.7.0 Retrieval Benchmark Rigor** — the deterministic retrieval track; deferred to the ROADMAP Backlog and does not gate this milestone.
- **BM25-vs-vanilla-RAG re-baselining** — the external review's framing; BM25 is the incumbent v0.6.0 replaced, already the counterfactual (`bench/BENCHMARKING_SCOPE.md`).
- **Curated hand-authored wiki articles** — the wiki corpus is *generated* by the distiller from memory; hand-authoring bypasses the compounding architecture WIKI-03 exists to prove.
- **New runtime dependencies in the core install** — the semantic path stays behind the optional `[semantic]` extra; default install stays dep-free.

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| TAX-01 | Phase 19 | Complete |
| TAX-02 | Phase 19 | Complete |
| TAX-03 | Phase 19 | Complete |
| TAX-04 | Phase 19 | Complete |
| IND-01 | Phase 20 | Complete |
| IND-02 | Phase 20 | Complete |
| IND-03 | Phase 20 | Complete |
| WIKI-03 | Phase 21 | Complete |
| WIKI-04 | Phase 21 | Complete |
| WIKI-05 | Phase 21 | Complete |
| WIKI-06 | Phase 21 | Complete |
| VERD-01 | Phase 22 | Complete |
| VERD-02 | Phase 22 | Complete |
| VERD-03 | Phase 22 | Complete |
