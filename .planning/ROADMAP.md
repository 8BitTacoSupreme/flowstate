# Roadmap: FlowState

## Milestones

- ✅ **v0.3.0 v2 Pivot + Operate-Safely** — Phases 1-2 (shipped 2026-06-06)
- ✅ **v0.4.0 Context Compaction & Compounding** — Phases 3-5 (shipped 2026-06-06)
- 🔄 **v0.5.0 Compounding Loop** — Phases 6-8 (in progress)

## Phases

<details>
<summary>✅ v0.3.0 v2 Pivot + Operate-Safely (Phases 1-2) — SHIPPED 2026-06-06</summary>

- [x] Phase 1: Land the v2 Pivot (direct commits) — completed 2026-05-25 (b38bbd6)
- [x] Phase 2: Operate Safely (4/4 plans) — completed 2026-05-25

Full detail: [`milestones/v0.3.0-ROADMAP.md`](./milestones/v0.3.0-ROADMAP.md)

</details>

<details>
<summary>✅ v0.4.0 Context Compaction & Compounding (Phases 3-5) — SHIPPED 2026-06-06</summary>

- [x] Phase 3: Ingredients — Pack, Canon, Fixtures (3/3 plans) — completed 2026-06-06
- [x] Phase 4: Integration — Layered CAG Assembly + Cache Lean-In (1/1 plan) — completed 2026-06-06
- [x] Phase 5: UX — Guided Kickoff + Hygiene (2/2 plans) — completed 2026-06-06

Full detail: [`milestones/v0.4.0-ROADMAP.md`](./milestones/v0.4.0-ROADMAP.md)

</details>

### v0.5.0 Compounding Loop (Phases 6-8)

- [x] **Phase 6: Run Journal** — Append-only, delta-only per-run trail persisted to memory + RUNLOG.md; surfaced as `## Since Last Run` prefix layer (completed 2026-06-08)
- [ ] **Phase 7: Gotchas Accumulator** — Structured failures promoted to a deduped, capped persistent gotchas layer injected into every run's context prefix
- [ ] **Phase 8: Runnable Verification** — `flowstate verify` turns fixture gates into real checks; failures close the loop back into gotchas + journal

## Phase Details

### Phase 6: Run Journal
**Goal**: Each pipeline run leaves an append-only, delta-only trail the next run reads first.
**Depends on**: Phase 5 (v0.4 complete — builds on `context_prefix.py` + `MemoryStore`)
**Requirements**: RUN-01, RUN-02, RUN-03
**Success Criteria** (what must be TRUE):
  1. After a pipeline run completes, exactly one new entry exists in both `memory.db` (kind=run) and `.planning/RUNLOG.md` capturing run_id, steps+status, artifacts changed, and a one-line delta — with no LLM call involved.
  2. The context prefix passed to every bridge call includes a `## Since Last Run` section drawn from the last N run-journal entries, positioned after the `## Prior Knowledge` memory layer, and the section is absent (not an empty heading) when no journal entries exist.
  3. `flowstate journal` prints recent run entries newest-first in a readable format and exits 0 even when RUNLOG.md or memory.db is absent or empty.
  4. N (entries shown) is configurable; the default is documented and the layer never causes silent truncation of other prefix layers.
**Plans**: 3 plans
Plans:
- [x] 06-01-PLAN.md — MemoryKind.RUN + journal.py append_run_entry + orchestrator wiring (RUN-01)
- [x] 06-02-PLAN.md — `## Since Last Run` prefix layer + run_journal_prefix_entries config (RUN-02)
- [x] 06-03-PLAN.md — `flowstate journal` read command (RUN-03)
**UI hint**: no

### Phase 7: Gotchas Accumulator
**Goal**: Structured failures (verifier gaps, plan-checker findings, doctor diagnoses, executor deviations) become a deduped, capped, persistent gotchas layer injected into every run's context prefix.
**Depends on**: Phase 6 (shares the `build_context_prefix` layering pattern; both add memory kinds + a prefix layer)
**Requirements**: GOT-01, GOT-02, GOT-03
**Success Criteria** (what must be TRUE):
  1. A structured failure signal from any of the four bounded sources (verifier VERIFICATION.md gaps, plan-checker findings, doctor/repair diagnoses, executor deviations) is automatically captured into `memory.db` (kind=insight, tagged `gotcha`) and mirrored to `.planning/GOTCHAS.md` with source, first-seen, and last-seen fields — no raw transcript mining occurs.
  2. The context prefix passed to every bridge call includes a `## Gotchas` section drawn from the accumulated gotchas store, positioned before the `## Prior Knowledge` memory layer (cache-friendlier, near fixtures).
  3. Running the same failure signal twice does not create a duplicate entry — dedup is by normalized signature; the last-seen timestamp updates on re-encounter.
  4. The gotchas layer is bounded: a configurable token budget caps the injected set to most-recent/most-frequent N entries; entries can be pruned when resolved; the layer never grows the prefix beyond its budget.
**Plans**: 4 plans
Plans:
- [x] 07-01-PLAN.md — MemoryStore.update + gotchas.py core (signature/dedup/capture/mirror/harvest) (GOT-01, GOT-03)
- [x] 07-02-PLAN.md — `## Gotchas` prefix layer before memory + cap/budget participation (GOT-02, GOT-03)
- [x] 07-03-PLAN.md — `flowstate gotchas` list/prune CLI + doctor/repair capture (GOT-01, GOT-03)
- [ ] 07-04-PLAN.md — executor-failure capture + run_pipeline harvest + journal gotchas slot (GOT-01)
**UI hint**: no

### Phase 8: Runnable Verification
**Goal**: `flowstate verify` turns eval-fixture acceptance gates into real checks against produced artifacts; failures feed the gotchas accumulator and the run journal, closing the loop.
**Depends on**: Phase 7 (verify failures feed the GOT-01 accumulator) and Phase 6 (verify appends a RUN-01 journal entry)
**Requirements**: VER-01, VER-02
**Success Criteria** (what must be TRUE):
  1. `flowstate verify` reads `acceptance_gates` and `forbidden_actions` from every fixture under `.planning/fixtures/`, checks them against the produced artifacts, and prints a human-readable pass/fail report — pure Python, no LLM call.
  2. `flowstate verify` exits non-zero when any gate fails, making it composable in CI and pre-commit alongside `flowstate doctor`.
  3. A failed `flowstate verify` gate automatically creates or updates a gotchas entry (GOT-01) and appends a run-journal entry (RUN-01) — the next pipeline run sees both without any manual step.
  4. `flowstate verify` exits 0 (with a clear "no fixtures" message) when `.planning/fixtures/` is absent or empty, and never raises an unhandled exception on malformed fixture files.
**Plans**: TBD
**UI hint**: no

## Progress

| Phase                                  | Milestone | Plans Complete | Status      | Completed            |
| -------------------------------------- | --------- | -------------- | ----------- | -------------------- |
| 1. Land the v2 Pivot                   | v0.3.0    | direct         | Complete    | 2026-05-25 (b38bbd6) |
| 2. Operate Safely                      | v0.3.0    | 4/4            | Complete    | 2026-05-25           |
| 3. Ingredients — Pack, Canon, Fixtures | v0.4.0    | 3/3            | Complete    | 2026-06-06           |
| 4. Integration — Layered CAG Assembly  | v0.4.0    | 1/1            | Complete    | 2026-06-06           |
| 5. UX — Guided Kickoff + Hygiene       | v0.4.0    | 2/2            | Complete    | 2026-06-06           |
| 6. Run Journal                         | v0.5.0    | 3/3 | Complete   | 2026-06-08 |
| 7. Gotchas Accumulator                 | v0.5.0    | 3/4 | In Progress|  |
| 8. Runnable Verification               | v0.5.0    | 0/?            | Not started | -                    |
