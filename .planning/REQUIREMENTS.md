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

- [ ] **MECH-01**: The research adapter scores each generated topic section for groundedness against the active fixture's `retrieval_questions` and retries-or-discards a weak section within a bounded budget — Autoresearch's measure→keep/discard applied to **output** (not prompts; the "prompt self-improvement stays in bench/" decision is untouched). Discarded/kept sections are recorded.
- [ ] **MECH-02**: The strategy adapter's five evaluation dimensions become a **scored rubric**: the bridge call emits parseable per-dimension scores (0–10) and a verdict (ship/pivot/kill), which the adapter validates; an unparseable or missing rubric is a failure (HON-04).
- [ ] **MECH-03**: The discipline adapter **runs the project's tests** (captures pass/fail), reads **real git state** (dirty tree / branch / ahead-behind, not just `.git` existence), and checks hook **contents** (non-empty/executable, not just presence) — Superpowers' RED-GREEN gate, in pure Python + subprocess. The result feeds HON-01's required-set.

### Vendor & Surface (VEND)

- [ ] **VEND-01**: Gstack's MIT `SKILL.md` assets (`garrytan/gstack`, © Garry Tan) are vendored into `flowstate/skills/gstack/`, with the MIT attribution added to `NOTICE`.
- [ ] **VEND-02**: Superpowers' MIT skill assets (`obra/superpowers`, © Jesse Vincent) are vendored into `flowstate/skills/superpowers/`, with the MIT attribution added to `NOTICE`.
- [ ] **VEND-03**: `flowstate install-skills` (also invoked from `init`/`kickoff`) copies the vendored skills into the project's `.claude/skills/`, so the user installs nothing manually.
- [ ] **VEND-04**: `flowstate launch strategy` surfaces gstack's `/office-hours`, and `flowstate launch discipline` surfaces the superpowers TDD skill, when the vendored skills are installed — mirroring the existing `flowstate launch gsd <N>` delegation.
- [ ] **VEND-05**: README corrections caught in passing: test count `803 → 947`; the Superpowers acknowledgment URL `obra/claude-code-superpowers` (404) → `obra/superpowers`.

## Future Requirements

Acknowledged, deferred — not in this milestone's roadmap.

- **MECH-F1**: Wire the existing `bench/tune_loop.py` mine→propose→gate loop into the runtime — explicitly deferred; it reverses the locked "prompt self-improvement lives in bench/, never auto-applies" decision. Only revisit with a deliberate decision to change that.
- **VEND-F1**: Vendor the MIT GSD prompt-skill set for full self-containment — deferred; GSD-2 is a standalone TS CLI and PROJECT.md's Out-of-Scope rejects cross-harness packaging. GSD stays detect-and-delegate.
- **DEAD-F1**: Remove or wire the dead surface (`ClaudeBridge.invoke_skill` with zero callers, `output_format="json"` with zero callers, `include_layers`/wiki with no production caller) — the json path and wiki caller are v0.8.0 "Harness Tax & Value" work (SEED-001); `invoke_skill` removal is low-priority cleanup.
- **DEG-F1**: Log a visible warning when the `pack` CAG layer is silently dropped because repomix/`repomix-pack.xml` is absent (`context_prefix.py:405-411`).

## Out of Scope

| Feature | Reason |
|---------|--------|
| Full GSD vendoring / GSD-2 CLI integration | GSD-2 is a TypeScript CLI on the Pi SDK, not Python-vendorable; PROJECT.md explicitly rejects cross-harness packaging. FlowState generates GSD's context files and delegates via `flowstate launch gsd`. |
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
| MECH-01 | Phase 13 | Pending |
| MECH-02 | Phase 13 | Pending |
| MECH-03 | Phase 13 | Pending |
| VEND-01 | Phase 14 | Pending |
| VEND-02 | Phase 14 | Pending |
| VEND-03 | Phase 14 | Pending |
| VEND-04 | Phase 14 | Pending |
| VEND-05 | Phase 14 | Pending |

**Coverage:**
- Milestone requirements: 14 total
- Mapped to phases: 14 (12–14)
- Unmapped: 0

---
*Requirements defined: 2026-07-10*
