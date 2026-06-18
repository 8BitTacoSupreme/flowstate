# Roadmap: FlowState

## Milestones

- ✅ **v0.3.0 v2 Pivot + Operate-Safely** — Phases 1-2 (shipped 2026-06-06)
- ✅ **v0.4.0 Context Compaction & Compounding** — Phases 3-5 (shipped 2026-06-06)
- ✅ **v0.5.0 Compounding Loop** — Phases 6-8 (shipped 2026-06-09)
- 🚧 **v0.6.0 Semantic Retrieval** — Phases 9-11 (in progress)

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

<details>
<summary>✅ v0.5.0 Compounding Loop (Phases 6-8) — SHIPPED 2026-06-09</summary>

- [x] Phase 6: Run Journal (3/3 plans) — completed 2026-06-08
- [x] Phase 7: Gotchas Accumulator (4/4 plans) — completed 2026-06-08
- [x] Phase 8: Runnable Verification (3/3 plans) — completed 2026-06-09

Full detail: [`milestones/v0.5.0-ROADMAP.md`](./milestones/v0.5.0-ROADMAP.md)

</details>

### 🚧 v0.6.0 Semantic Retrieval (In Progress)

**Milestone Goal:** Replace FTS5/BM25 with sqlite-vec semantic KNN across the memory and wiki layers, recovering the proven ~0.82 grounding accuracy. Optional [semantic] extra; byte-identical FTS5 fallback when the embedder is absent.

- [x] **Phase 9: Embedding Provider + Vector Store Foundation** — New `flowstate/embeddings.py` optional provider + `vec0` virtual table in `memory.db` with embed-on-add/update and lazy backfill (completed 2026-06-18)
- [x] **Phase 10: Semantic Memory Retrieval** — Wire semantic KNN into `MemoryStore.get_context()` with byte-compatible FTS5 fallback (completed 2026-06-18)
- [ ] **Phase 11: Semantic Wiki Retrieval** — Wire per-run semantic top-k wiki retrieval into `context_prefix` with byte-identical default path preserved

## Phase Details

### Phase 9: Embedding Provider + Vector Store Foundation
**Goal**: The optional embedding layer and its backing vector store exist — semantic vectors can be computed, persisted, and queried when the [semantic] extra is installed, and every path degrades silently to FTS5-only when it is not.
**Depends on**: Phase 8 (v0.5.0 complete)
**Requirements**: EMB-01, EMB-02, EMB-03, EMB-04, VEC-01, VEC-02, VEC-03
**Success Criteria** (what must be TRUE):
  1. `from flowstate.embeddings import get_embedder` succeeds on a bare (no fastembed) install and `get_embedder().available()` returns False without raising
  2. With `pip install flowstate[semantic]`, `get_embedder().available()` returns True and `get_embedder().embed(["hello"])` returns a list of 384-dim float vectors
  3. `memory.db` contains a `memories_vec` (vec0) virtual table after `MemoryStore` opens on any existing database, without any migration command
  4. `MemoryStore.add()` silently skips vector writes when the embedder is absent; when present, the added entry has a corresponding embedding row in `memories_vec`
  5. Opening a `MemoryStore` with existing rows and an available embedder backfills missing vectors without blocking startup or raising
**Plans**: 2 plans
  - [x] 09-01-PLAN.md — Embedding provider module (`flowstate/embeddings.py`) + `[semantic]` pip extra (EMB-01..04)
  - [x] 09-02-PLAN.md — vec0 store on `MemoryStore`: load sqlite-vec, `memories_vec` table, embed-on-write + lazy backfill (VEC-01..03)

### Phase 10: Semantic Memory Retrieval
**Goal**: `MemoryStore.get_context()` surfaces the most semantically relevant memories when vectors exist, and falls back to the unchanged FTS5/BM25 path when they do not — same `## Prior Knowledge` block format either way.
**Depends on**: Phase 9
**Requirements**: MEM-01, MEM-02
**Success Criteria** (what must be TRUE):
  1. `get_context(query)` with an available embedder returns memories ranked by KNN cosine distance (k≈3–5), not BM25 rank
  2. `get_context(query)` with no embedder or no vectors returns a `## Prior Knowledge` block whose content is byte-identical to the current FTS5 output for the same store state
  3. All existing golden tests for `get_context` output format pass unchanged after this phase ships
  4. Tests cover both the semantic and fallback paths using an injected fake embed_fn (no network/model required)
**Plans**: 1 plan
  - [x] 10-01-PLAN.md — Semantic KNN in `get_context()` with byte-identical FTS5 fallback + offline tests (MEM-01, MEM-02)

### Phase 11: Semantic Wiki Retrieval
**Goal**: The `context_prefix` wiki layer retrieves the most semantically relevant articles per run rather than reading the full static wiki file — while leaving the default (no `include_layers`) path entirely untouched.
**Depends on**: Phase 9
**Requirements**: WIKI-01, WIKI-02
**Success Criteria** (what must be TRUE):
  1. When the `wiki` layer is active and the embedder is available, `build_context_prefix()` injects only the top-k semantically retrieved wiki articles (not the full file) into the prefix
  2. When the `wiki` layer is active and the embedder is absent, `build_context_prefix()` falls back to the existing `_read_wiki_layer` static-read behavior without raising
  3. The default `build_context_prefix()` call (no `include_layers`) produces output that is byte-identical to pre-Phase-11 output — golden tests pass unmodified
  4. Tests cover the semantic retrieval path with a fake embed_fn and a small in-memory wiki corpus (no network/model required)
**Plans**: TBD

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Land the v2 Pivot | v0.3.0 | direct | Complete | 2026-05-25 (b38bbd6) |
| 2. Operate Safely | v0.3.0 | 4/4 | Complete | 2026-05-25 |
| 3. Ingredients — Pack, Canon, Fixtures | v0.4.0 | 3/3 | Complete | 2026-06-06 |
| 4. Integration — Layered CAG Assembly | v0.4.0 | 1/1 | Complete | 2026-06-06 |
| 5. UX — Guided Kickoff + Hygiene | v0.4.0 | 2/2 | Complete | 2026-06-06 |
| 6. Run Journal | v0.5.0 | 3/3 | Complete | 2026-06-08 |
| 7. Gotchas Accumulator | v0.5.0 | 4/4 | Complete | 2026-06-08 |
| 8. Runnable Verification | v0.5.0 | 3/3 | Complete | 2026-06-09 |
| 9. Embedding Provider + Vector Store Foundation | v0.6.0 | 2/2 | Complete   | 2026-06-18 |
| 10. Semantic Memory Retrieval | v0.6.0 | 1/1 | Complete   | 2026-06-18 |
| 11. Semantic Wiki Retrieval | v0.6.0 | 0/TBD | Not started | - |
