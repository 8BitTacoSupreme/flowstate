# Handoff: Wire sqlite-vec Semantic Retrieval into FlowState's Memory/Wiki Layer

Self-contained handoff to productionize the retrieval design the bench just proved. A fresh
session should be able to execute this without re-deriving. Treat as authoritative spec; verify
line/function refs against current code before editing (they're named, not line-pinned).

## Why (the proven result — do not re-litigate)

Bench experiments (see memory `compounding-experiment-n6-result` + `bench/grounding.py`) established,
on a real Confluent-domain target (`/tmp/fb_cflt`, the cflt-ai wiki) with a **checkable grounding
eval** (binary, multi-judge, Wilson CIs):

- **Distilled knowledge in context works.** Oracle (hand-placed relevant wiki articles): grounding
  accuracy **0.80–0.83** vs **none 0.05–0.20** (disjoint CIs). Decisive.
- **Naive BM25/FTS5 retrieval fails.** `wikirag` arm: **0.425**, surfaced the correct article only
  **3/20** (lexical density ≠ fact location). This also explains the old "raw-memory FTS5 null."
- **Semantic retrieval solves it.** `wikivec` arm (sqlite-vec KNN over fastembed bge-small-en-v1.5,
  384-dim): **0.825 ≈ oracle**, surfaced the correct article **17/20** at k=3. Full recovery.

**Conclusion:** the production-viable context strategy is **distilled-knowledge + SEMANTIC retrieval**.
`sqlite-vec` is ALREADY a FlowState dependency (`pyproject.toml`, currently unused). The only new
piece is an embedding provider.

Reference implementation to PORT: `bench/grounding.py` → `_default_embedder()` (lazy fastembed seam)
and `_retrieve_vec()` (vec0 KNN: `CREATE VIRTUAL TABLE ... USING vec0(embedding float[384])`,
`sqlite_vec.serialize_float32(vec)`, `SELECT rowid, distance FROM vec_docs WHERE embedding MATCH ?
ORDER BY distance LIMIT k`). Smoke-confirmed: `import sqlite_vec; sqlite_vec.load(conn)` works (v0.1.9).

## Decisions to make FIRST (surface to the user — these change the build)

1. **Embedding provider + the no-new-runtime-deps constraint (the big one).**
   - `fastembed` (ONNX, no torch; pulls onnxruntime + tokenizers + huggingface-hub; downloads a
     ~130MB model on first use) is bench-proven and offline/local.
   - This VIOLATES the milestone "no new runtime dependencies" rule → this is almost certainly a
     **new milestone** (`/gsd-new-milestone`), not a quick task.
   - **Recommended:** make it an **optional dependency** with graceful fallback — semantic retrieval
     activates only if the embedder is importable; otherwise fall back to today's FTS5/BM25. Keeps
     core install dep-free, makes the upgrade opt-in. (`pyproject` optional-extra `[semantic]`.)
   - Alternative: external embeddings API (needs a key — only EXA is present today, and Exa has no
     general text-embeddings endpoint, so this needs an OpenAI/Voyage key the user must provide).

2. **What gets semantically retrieved** (two seams, both proven analogous):
   - **(a) Memory layer** — `MemoryStore.get_context(query)` currently does FTS5 BM25 over `memories`
     and returns the `## Prior Knowledge` block. Add semantic KNN here. (Directly fixes the
     "raw-memory FTS5 null".)
   - **(b) Wiki layer** — `context_prefix.py::_read_wiki_layer()` currently reads a static
     `.planning/codebase/wiki.md`. Replace/augment with **per-run semantic retrieval** over an
     embedded wiki corpus (the proven win). This is the higher-value one.
   - **Recommended:** do BOTH on a shared vector store; they're the same mechanism.

3. **Where the production wiki comes from.** The cflt-ai wiki was hand/LLM-maintained. FlowState
   options: (i) `bench/wikigen.py`-style pack digest (code-derived — proven only an efficiency win,
   not a quality lift); (ii) an **evolving distilled-knowledge wiki** (the user's "knowledge ≠ code"
   vision: gotchas/decisions/do-not-do/rationale curated over runs — this is what the grounding
   result actually validated). Recommend (ii) as the real target; (i) as a bootstrap.

## Proposed architecture

**Vector store (extend `memory.db`):**
- Load sqlite-vec on the existing `MemoryStore._conn`: `conn.enable_load_extension(True);
  import sqlite_vec; sqlite_vec.load(conn)`.
- Add a `vec0` virtual table, e.g. `CREATE VIRTUAL TABLE memories_vec USING vec0(embedding float[D])`
  keyed by the memory rowid/id. (D = embedder dim, e.g. 384 for bge-small.)
- Compute + store the embedding in `MemoryStore.add()` (and on update). Guard so it's a no-op when
  the embedder is absent (fallback mode).

**Retrieval (`get_context` / wiki layer):**
- Embed the query; KNN `WHERE embedding MATCH serialize_float32(qvec) ORDER BY distance LIMIT k`;
  map rowids → entries; format as today's `## Prior Knowledge` block.
- **Fallback:** if no embedder / no vectors, use the existing FTS5 path unchanged. Same public API.
- Default k≈3–5 (k=3 gave 17/20 in the experiment). Keep the existing token-budget trimming.

**Embedder module** (`flowstate/embeddings.py`, new): lazy provider, `embed(texts)->list[list[float]]`,
`dim` property, `available()->bool`. Port `_default_embedder` from `bench/grounding.py`. One model,
configurable via config/env (mirror the `FLOWSTATE_CONTEXT_BUDGET_TOKENS` env-override pattern in
`context_prefix._load_budget`).

**Wiki layer semantic mode:** generalize the bench `wikivec` path — embed a wiki corpus (articles
under `.planning/codebase/wiki/` or wherever the production wiki lives) into a vec0 table; per build
of the prefix, retrieve top-k by the run's `_pk_query` and inject those (replacing the static
`_read_wiki_layer` read, or as a new layer key). Keep it opt-in like the current `wiki` layer so the
default/None path stays byte-identical (there are golden tests guarding that — keep them green).

## Migration / backfill
- Adding `memories_vec` is additive; existing `memory.db` files need a one-time **backfill**: on open,
  if vectors are missing for existing rows AND an embedder is available, embed lazily (or a
  `flowstate` maintenance command). Never block startup; degrade to FTS5 if embedder absent.
- Bump state/schema version if you add config keys; FlowState has a migration ladder in
  `flowstate/state.py` (v0.1→…). Confirm `--cov-fail-under=80` stays satisfied.

## Test plan (mirror existing patterns; tests must NOT require the model/network)
- Inject a fake embedder (deterministic vectors) — the bench tests in `tests/test_bench_grounding.py`
  show the pattern (`embed_fn` injected, `sqlite_vec` guarded with skipif).
- Cover: vectors written on `add()`; KNN returns nearest; **FTS5 fallback when embedder absent**;
  `get_context` byte-compatible block format; backfill path; context_prefix golden test still
  byte-identical on the default path.
- Gate: `.venv/bin/python -m pytest tests/ --cov=flowstate --cov-fail-under=80`; ruff check + format.

## Suggested GSD entry
This is milestone-sized (runtime dep + schema + migration + two integration seams). Recommend
`/gsd-new-milestone` ("Semantic retrieval") → `/gsd-plan-phase`, OR a focused `/gsd-quick` per seam
if the embedder-dep decision is settled as "optional + fallback". Start by getting the user's call on
Decision #1 (embedder dep) — everything else follows.

## Key files (verify against current code)
- `flowstate/memory.py` — `MemoryStore` (FTS5 schema `memories_fts`, `add()`, `get_context()`,
  `_sanitize_fts_query()`). Retrieval seam (a).
- `flowstate/context_prefix.py` — `build_context_prefix()`, `_read_wiki_layer()` (opt-in wiki layer,
  reads `.planning/codebase/wiki.md`), `_load_budget()` (env-override pattern to mirror). Seam (b).
- `bench/grounding.py` — `_default_embedder()`, `_retrieve_vec()`, `_retrieve_wiki()` (BM25 baseline),
  the `wikivec`/`wikirag` arm dispatch. **Reference implementation to port.**
- `pyproject.toml` — `sqlite-vec` already present; add optional `[semantic]` extra for the embedder.
- Evidence: memory `compounding-experiment-n6-result` (full arc + numbers); `bench/PAIRED_DESIGN_RUNBOOK.md`.

## Bench rig still available for validation
`bench/grounding.py` arms `none/pack/wiki/memory/full/wikirag/wikivec`; probes pattern in
`/tmp/fb_cflt_probes.json` (ephemeral — regenerate from cflt-ai wiki if gone). Use it to A/B the
production semantic path against the bench `wikivec` baseline (expect ~0.82 grounding accuracy).
