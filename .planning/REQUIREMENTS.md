# Requirements: FlowState — v0.6.1 Make the Names Real

**Defined:** 2026-07-10
**Core Value:** Each run starts smarter than the last. But a run can only compound if it can tell success from failure — and today FlowState's enforcement stage cannot fail, and two adapters report success on total failure. v0.6.1 makes the pipeline honest and makes the `research`/`strategy`/`discipline` adapters actually do the mechanism their namesakes (Autoresearch / Gstack / Superpowers) are built on, before any further harness benchmarking.

## Milestone v0.6.1 Requirements

Each maps to exactly one roadmap phase.

### Honesty & Failure-Capability (HON)

- [ ] **HON-01**: `discipline.check_setup()` derives `AuditResult.success` from the checks against a required-set (at minimum: git repo present + a test config present), not a hardcoded `True`; a repo missing the required-set returns `success=False`.
- [ ] **HON-02**: The orchestrator reads `audit.success`; a failed audit marks the Discipline step `BLOCKED` (not `COMPLETED`), and `_print_summary` reflects it. A `flowstate discipline` CLI subcommand exits non-zero on audit failure (mirroring `flowstate verify`).
- [ ] **HON-03**: `research.py::execute()` returns `ToolResult(success=False, error=...)` when all topics (or a configurable threshold) fail their bridge calls; "*Research failed*" notices never coexist with `success=True`.
- [ ] **HON-04**: `strategy.py::execute()` returns `ToolResult(success=False)` when its bridge call fails or returns empty, rather than writing a failed/empty artifact and reporting success.
- [ ] **HON-05**: A live (non-`--dry-run`) run with no locatable `claude` CLI marks the affected steps `BLOCKED` and does not write bridge stub text (`[dry-run] claude prompt...`) as a real artifact — the run fails loud.
- [ ] **HON-06**: `gsd_adapter.py`'s "optional LLM enrichment" docstring is reconciled with the code — either the enrichment is implemented or the claim is removed.

### Adapter Mechanisms (MECH)

- [x] **MECH-01**: The research adapter scores each generated topic section for groundedness against the active fixture's `retrieval_questions` and retries-or-discards a weak section within a bounded budget — Autoresearch's measure→keep/discard applied to **output** (not prompts; the "prompt self-improvement stays in bench/" decision is untouched). Discarded/kept sections are recorded.
- [x] **MECH-02**: The strategy adapter's five evaluation dimensions become a **scored rubric**: the bridge call emits parseable per-dimension scores (0–10) and a verdict (ship/pivot/kill), which the adapter validates; an unparseable or missing rubric is a failure (HON-04).
- [x] **MECH-03**: The discipline adapter **runs the project's tests** (captures pass/fail), reads **real git state** (dirty tree / branch / ahead-behind, not just `.git` existence), and checks hook **contents** (non-empty/executable, not just presence) — Superpowers' RED-GREEN gate, in pure Python + subprocess. The result feeds HON-01's required-set.

### Vendor & Surface (VEND)

- [x] **VEND-01**: Gstack's MIT `SKILL.md` assets (`garrytan/gstack`, © Garry Tan) are vendored into `flowstate/skills/gstack/`, with the MIT attribution added to `NOTICE`.
- [x] **VEND-02**: Superpowers' MIT skill assets (`obra/superpowers`, © Jesse Vincent) are vendored into `flowstate/skills/superpowers/`, with the MIT attribution added to `NOTICE`.
- [x] **VEND-03**: `flowstate install-skills` (also invoked from `init`/`kickoff`) copies the vendored skills into the project's `.claude/skills/`, so the user installs nothing manually.
- [x] **VEND-04**: `flowstate launch strategy` surfaces gstack's `/office-hours`, and `flowstate launch discipline` surfaces the superpowers TDD skill, when the vendored skills are installed — mirroring the existing `flowstate launch gsd <N>` delegation.
- [x] **VEND-05**: **README reconciliation** — make every claim match the v0.6.1 code, landing in the same phase as the code that makes it true. (a) Factual bugs, independent of adapters: test count reconciled to the real `pytest --collect-only` count (985 at Wave 1; re-derived in 14-04); the Superpowers URL `obra/claude-code-superpowers` (404) → `obra/superpowers`; `flowstate doctor` "5 checks" → **6** (adds `stale_status`); the sqlite-vec + fastembed acknowledgment implies both are optional — sqlite-vec is a **core** dep, only fastembed is behind `[semantic]`. (b) Adapter Acknowledgments, now that Phase 13 makes them real: rewrite the Autoresearch/Gstack/Superpowers lines from "draws on the idea / implements a similar" to describe what the adapters *actually now do* (research measure→keep/discard over output; strategy scored rubric + verdict; discipline runs tests + real git state + hook contents that can fail). No claim may describe an unbuilt mechanism.

### Bundle GSD (GSD) — reverses the "no cross-harness packaging" decision (user-directed 2026-07-10)

- [x] **GSD-01**: A pinned GSD distribution — skills + `get-shit-done/` Node runtime + `gsd-sdk` CLI — is vendored into `flowstate/vendor/gsd/` from the canonical MIT repo (`gsd-build/get-shit-done`, © Lex Christopherson), with the upstream `LICENSE` captured verbatim and a recorded `VERSION`/commit for provenance. `NOTICE` carries the GSD MIT attribution.
- [ ] **GSD-02**: `flowstate install-skills` (extended from VEND-03) installs GSD **unconditionally** into the project's `.claude/skills/` + `.claude/get-shit-done/` and makes `gsd-sdk` invokable — no detection, no prompt, no separate user install.
- [ ] **GSD-03**: `flowstate launch gsd <N>` works against the vendored GSD with nothing separately installed; the launcher's GSD detect-and-suggest path is neutralized (GSD is assumed present because FlowState installed it).
- [ ] **GSD-04**: A documented refresh/staleness path for the pinned GSD (mirroring the `flowstate pack` manifest/staleness pattern) lets the vendored snapshot be updated deliberately, not silently.
- [ ] **GSD-05**: The GSD acknowledgment + install docs in README are updated to describe the bundled-and-auto-installed reality ("FlowState vendors and installs GSD; no separate GSD install required") rather than the old "generates the context files GSD consumes … hand off to native GSD execution" delegate-only framing. Prerequisites section drops "GSD (optional, install separately)".

## Future Requirements

Acknowledged, deferred — not in this milestone's roadmap.

- **MECH-F1**: Wire the existing `bench/tune_loop.py` mine→propose→gate loop into the runtime — explicitly deferred; it reverses the locked "prompt self-improvement lives in bench/, never auto-applies" decision. Only revisit with a deliberate decision to change that.
- **DEAD-F1**: Remove or wire the dead surface (`ClaudeBridge.invoke_skill` with zero callers, `output_format="json"` with zero callers, `include_layers`/wiki with no production caller) — the json path and wiki caller are v0.8.0 "Harness Tax & Value" work (SEED-001); `invoke_skill` removal is low-priority cleanup.
- **DEG-F1**: Log a visible warning when the `pack` CAG layer is silently dropped because repomix/`repomix-pack.xml` is absent (`context_prefix.py:405-411`).

## Out of Scope

| Feature | Reason |
|---------|--------|
| Codex / OpenCode / Cursor **adapters** (running FlowState *on* other host harnesses) | Still out of scope. The 2026-07-10 reversal bundles GSD (a tool FlowState delegates *to*); it does not open FlowState to other host harnesses. GSD-2/gsd-pi's TS CLI is not what we vendor — GSD-01 vendors the MIT `get-shit-done` skill+runtime distribution FlowState already uses. |
| Prompt self-modification in the runtime | Locked PROJECT.md decision: prompt tuning lives in `bench/`, is eval-gated, never auto-applies. MECH-01 loops over *output*, not prompts. |
| Reimplementing gstack's full 23-skill / superpowers' full methodology in Python | The adapters implement each namesake's core *mechanism*; the full skill suites are surfaced by vendoring + `flowstate launch`, not reimplemented in-process. |
| New runtime dependencies | Vendored skills are markdown assets, not Python imports; the mechanisms use stdlib + subprocess + the existing `claude --print` bridge. The dep-free-default install is untouched. |
| The v0.8.0 dead-surface + Tax work | `output_format="json"` accounting and `include_layers={"wiki"}` activation are SEED-001 / v0.8.0. |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| HON-01 | Phase 12 | Pending |
| HON-02 | Phase 12 | Pending |
| HON-03 | Phase 12 | Pending |
| HON-04 | Phase 12 | Pending |
| HON-05 | Phase 12 | Pending |
| HON-06 | Phase 12 | Pending |
| MECH-01 | Phase 13 | Complete |
| MECH-02 | Phase 13 | Complete |
| MECH-03 | Phase 13 | Complete |
| VEND-01 | Phase 14 | Complete |
| VEND-02 | Phase 14 | Complete |
| VEND-03 | Phase 14 | Complete |
| VEND-04 | Phase 14 | Complete |
| VEND-05 | Phase 14 | Complete |
| GSD-01 | Phase 15 | Complete |
| GSD-02 | Phase 15 | Pending |
| GSD-03 | Phase 15 | Pending |
| GSD-04 | Phase 15 | Pending |
| GSD-05 | Phase 15 | Pending |

**Coverage:**
- Milestone requirements: 19 total
- Mapped to phases: 19 (12–15)
- Unmapped: 0

---
*Requirements defined: 2026-07-10*
