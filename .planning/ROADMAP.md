# Roadmap: FlowState

## Milestones

- ✅ **v0.3.0 v2 Pivot + Operate-Safely** — Phases 1-2 (shipped 2026-06-06)
- [ ] **v0.4.0 Context Compaction & Compounding** — Phases 3-5 (in progress)

## Phases

<details>
<summary>✅ v0.3.0 v2 Pivot + Operate-Safely (Phases 1-2) — SHIPPED 2026-06-06</summary>

- [x] Phase 1: Land the v2 Pivot (direct commits) — completed 2026-05-25 (b38bbd6)
- [x] Phase 2: Operate Safely (4/4 plans) — completed 2026-05-25

Full detail: [`milestones/v0.3.0-ROADMAP.md`](./milestones/v0.3.0-ROADMAP.md)

</details>

### v0.4.0 Context Compaction & Compounding

- [ ] **Phase 3: Ingredients** — Pack, Canon, and Fixtures exist as independently-testable artifacts before anything composes them
- [ ] **Phase 4: Integration** — Layered CAG assembly with cache-optimized prefix built once per run; repomix-MCP overflow path
- [ ] **Phase 5: UX** — Scaffold-only `flowstate kickoff` command + SUMMARY `status:` frontmatter standardization

## Phase Details

### Phase 3: Ingredients — Pack, Canon, Fixtures
**Goal**: The three new context sources (Repomix pack, Karpathy canon, ECC-modeled fixtures) exist as durable artifacts and constants, each independently testable, before any composition layer is built.
**Depends on**: Phase 2 (v0.3.0 complete)
**Requirements**: PACK-01, PACK-02, PACK-03, CANON-01, FIX-01, FIX-02, DX-02
**Success Criteria** (what must be TRUE):
  1. `flowstate pack` produces `.planning/codebase/repomix-pack.xml`, registers it on `install_manifest` with a checksum, and exits with a clear error (non-zero) when repomix is not found in PATH or `FLOWSTATE_REPOMIX_BIN`
  2. Running `flowstate pack` a second time reuses the existing pack when no source file is newer than the pack's `created_at`; a source-file touch triggers a regeneration
  3. `.mcp.json` contains a repomix-MCP entry, and `ClaudeBridge` passes it through `--allowed-tools` when spawning agents
  4. Every `claude --print` invocation has the Karpathy canon block prepended to its system prompt; setting `BridgeConfig.inject_canon = False` suppresses it
  5. `flowstate init` (and later `kickoff`) writes a starter fixture under `.planning/fixtures/` registered on `install_manifest`; the fixture file includes `retrieval_questions`, `acceptance_gates`, `forbidden_actions`, a system contract, and at least one few-shot exemplar
**Plans**: 3 plans
Plans:
- [x] 03-01-PLAN.md — Repomix pack: locator + run_pack + staleness + `flowstate pack` CLI + InstallEntry kind (PACK-01/02/03)
- [x] 03-02-PLAN.md — Karpathy CANON constant + `inject_canon` flag prepended to every claude --print system prompt (CANON-01)
- [x] 03-03-PLAN.md — ECC-modeled starter fixture + `.mcp.json` registration + repomix-pack CLAUDE.md guidance (FIX-01/02, DX-02)
**UI hint**: no

### Phase 4: Integration — Layered CAG Assembly + Cache Lean-In
**Goal**: The orchestrator composes fixtures → pack (if it fits) → memory into one ordered, cache-optimized user-prompt prefix built once per run (canon already ships in the bridge system prompt from Phase 3), with repomix-MCP retrieval as the overflow path; the m9v byte-identical-prefix cache behavior is preserved.
**Depends on**: Phase 3
**Requirements**: CAG-01, CAG-02, CAG-03
**Success Criteria** (what must be TRUE):
  1. A single `build_context_prefix()` call returns an ordered string (fixtures → pack if it fits → memory) that is threaded into all adapters via the existing `prior_knowledge` seam — no adapter calls `build_context_prefix()` independently (canon ships in the bridge system prompt, NOT in this user-prompt prefix, per the CAG-01 locked decision — re-emitting it would double-inject)
  2. When the pack pushes the prefix over budget, `build_context_prefix()` retries with `repomix --compress`; if still over, it omits the pack entirely and logs the decision — no content is silently dropped
  3. Consecutive runs against the same codebase produce an identical prefix byte-for-byte up to the memory section, confirming the stable-prefix cache property; bridge docs describe the cache behavior and `ENABLE_PROMPT_CACHING_1H` opt-in
**Plans**: 1 plan
Plans:
- [ ] 04-01-PLAN.md — build_context_prefix() assembler (fixtures→pack→memory) + fit/compress/omit ladder + orchestrator seam threading + ENABLE_PROMPT_CACHING_1H opt-in (CAG-01/02/03)
**UI hint**: no

### Phase 5: UX — Guided Kickoff + Hygiene
**Goal**: A fast scaffold-only `flowstate kickoff` (no LLM pipeline) plus SUMMARY `status:` frontmatter standardization across existing quick tasks.
**Depends on**: Phase 4 (soft — kickoff scaffolds pack + fixture from Phases 3-4)
**Requirements**: KICK-01, KICK-02, DX-01
**Success Criteria** (what must be TRUE):
  1. `flowstate kickoff` runs the enhanced interview, writes scaffold artifacts (context files, pack, starter fixture), and exits without invoking any LLM pipeline step
  2. The interview questions added for kickoff are also present in the full `flowstate init` flow — no divergence between the two entry points
  3. The two existing quick-task SUMMARY files carry a `status:` field (`complete`, `verified`, `blocked`, `paused`, or `drafted`); `audit-open` no longer false-flags them as in-flight
**Plans**: TBD
**UI hint**: no

## Progress

| Phase                                           | Milestone | Plans Complete | Status      | Completed |
| ----------------------------------------------- | --------- | -------------- | ----------- | --------- |
| 1. Land the v2 Pivot                            | v0.3.0    | direct         | Complete    | 2026-05-25 (b38bbd6) |
| 2. Operate Safely                               | v0.3.0    | 4/4            | Complete    | 2026-05-25 |
| 3. Ingredients — Pack, Canon, Fixtures          | v0.4.0    | 3/3 | Complete   | 2026-06-06 |
| 4. Integration — Layered CAG Assembly           | v0.4.0    | 0/1            | Not started | - |
| 5. UX — Guided Kickoff + Hygiene                | v0.4.0    | 0/?            | Not started | - |
