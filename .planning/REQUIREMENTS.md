# Requirements: FlowState — v0.6.0 Semantic Retrieval

**Defined:** 2026-06-18
**Core Value:** Each run starts smarter than the last — durable artifacts + auto-injected memory make work compound across runs. v0.6.0 fixes the retrieval bottleneck so the *right* prior knowledge actually surfaces.

## Milestone v0.6.0 Requirements

Requirements for this milestone. Each maps to exactly one roadmap phase.

### Embedding Provider (EMB)

- [ ] **EMB-01**: A `flowstate/embeddings.py` module exposes a lazy embedding provider with `embed(texts) -> list[list[float]]`, a `dim` property, and `available() -> bool`; importing the module never requires fastembed to be installed.
- [ ] **EMB-02**: The embedding model is configurable via env var (mirroring the `FLOWSTATE_CONTEXT_BUDGET_TOKENS` precedence pattern) and/or `.planning/config.json`, defaulting to `BAAI/bge-small-en-v1.5` (384-dim).
- [ ] **EMB-03**: fastembed is declared as an optional `[semantic]` pip extra in `pyproject.toml`; the core install remains dependency-free.
- [ ] **EMB-04**: When the embedder is unavailable (extra not installed or import fails), `available()` returns False and every caller degrades gracefully without raising.

### Vector Store (VEC)

- [ ] **VEC-01**: `memory.db` gains a `vec0` virtual table keyed to memory rows, with sqlite-vec loaded on the existing `MemoryStore` connection.
- [ ] **VEC-02**: `MemoryStore.add()` and `update()` compute and persist the row embedding when an embedder is available, and are a silent no-op (FTS5-only) when it is absent.
- [ ] **VEC-03**: On store open, existing rows missing vectors are lazily backfilled when an embedder is available; open never blocks and never fails when the embedder is absent.

### Memory Retrieval (MEM)

- [ ] **MEM-01**: `MemoryStore.get_context()` returns semantic-KNN-ranked memories (default k≈3–5) when vectors and an embedder are available.
- [ ] **MEM-02**: `get_context()` falls back to the existing FTS5/BM25 path when no embedder/vectors are present, producing a `## Prior Knowledge` block byte-compatible with today's output.

### Wiki Retrieval (WIKI)

- [ ] **WIKI-01**: The `context_prefix` wiki layer retrieves the top-k most-relevant wiki articles semantically per run (by the run's query) over an embedded wiki corpus, replacing the static full-file read when semantic mode is active.
- [ ] **WIKI-02**: The default (no `include_layers`) context-prefix path stays byte-identical (wiki remains opt-in, golden tests stay green); semantic wiki retrieval degrades to the existing static `_read_wiki_layer` read when the embedder is absent.

## Future Requirements

Acknowledged, deferred — not in this milestone's roadmap.

### Embedding Provider

- **EMB-F1**: External/hosted embeddings backend (OpenAI/Voyage) as an alternative provider — deferred; needs a user-provisioned API key and adds per-call network cost. Optional-local-fastembed covers the proven path.
- **EMB-F2**: Multiple/swappable embedding models with dimension negotiation at runtime — single configurable model is sufficient for v0.6.

### Wiki Retrieval

- **WIKI-F1**: An evolving distilled-knowledge wiki curated across runs (gotchas/decisions/rationale) as the semantic corpus source — the higher-value long-term target; v0.6 ships the retrieval mechanism over whatever corpus exists (code-derived bootstrap acceptable).

## Out of Scope

| Feature | Reason |
|---------|--------|
| fastembed as a **core** dependency | Violates the dep-free-default rule; pulls ~200MB transitive deps + a model download on every install. Optional `[semantic]` extra + FTS5 fallback chosen instead. |
| Reranking / hybrid lexical+semantic fusion | Pure semantic KNN already recovered oracle-level grounding (0.825 ≈ 0.800) in the bench; fusion is unjustified complexity until measured to help. |
| Re-embedding the repomix pack / general code retrieval | Bench showed raw code (pack) ≈ none; the proven lift is distilled-knowledge + semantic retrieval, not code embedding. |
| GPU / batching / embedding-cache performance tuning | FlowState's corpus is small (memories + a wiki); correctness and graceful fallback matter more than throughput at this scale. |
| Changing the `flowstate.json` state schema | v0.6 changes only `memory.db` (additive `vec0` table); state model and its migration ladder stay untouched. |

## Traceability

Which phases cover which requirements. Populated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| EMB-01 | TBD | Pending |
| EMB-02 | TBD | Pending |
| EMB-03 | TBD | Pending |
| EMB-04 | TBD | Pending |
| VEC-01 | TBD | Pending |
| VEC-02 | TBD | Pending |
| VEC-03 | TBD | Pending |
| MEM-01 | TBD | Pending |
| MEM-02 | TBD | Pending |
| WIKI-01 | TBD | Pending |
| WIKI-02 | TBD | Pending |

**Coverage:**
- Milestone requirements: 11 total
- Mapped to phases: 0 (pending roadmap)
- Unmapped: 11 ⚠️

---
*Requirements defined: 2026-06-18*
*Last updated: 2026-06-18 after initial definition*
