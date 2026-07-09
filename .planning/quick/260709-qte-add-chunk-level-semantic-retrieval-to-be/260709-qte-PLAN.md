---
phase: quick-260709-qte
plan: 01
type: tdd
wave: 1
depends_on: []
files_modified:
  - bench/_retrieval.py
  - bench/longmemeval.py
  - tests/test_retrieval_chunked.py
  - tests/test_longmemeval.py
autonomous: true
requirements: [QTE-01]
must_haves:
  truths:
    - "A doc whose SECOND chunk matches the query ranks first under chunked retrieval (fails under plain semantic_rank which sees only the truncated head)"
    - "semantic_rank_chunked never raises — returns [] on missing sqlite_vec or embed failure"
    - "--chunk-tokens 0 reproduces today's output byte-identically (uses semantic_rank, not chunked)"
    - "--chunk-tokens N>0 with semantic backend uses semantic_rank_chunked and records chunk_tokens in JSON"
  artifacts:
    - path: bench/_retrieval.py
      provides: "semantic_rank_chunked() with max-sim rollup"
      contains: "def semantic_rank_chunked"
    - path: bench/longmemeval.py
      provides: "--chunk-tokens flag + chunked ranker wiring"
      contains: "chunk-tokens"
    - path: tests/test_retrieval_chunked.py
      provides: "chunking / rollup / dedup / never-raises tests"
  key_links:
    - from: bench/longmemeval.py
      to: bench._retrieval.semantic_rank_chunked
      via: "module-attribute access _retrieval.semantic_rank_chunked(...)"
      pattern: "_retrieval\\.semantic_rank_chunked"
---

<objective>
Fix a measured truncation bug: 94.6% of LongMemEval sessions exceed bge's 512-token cap (median 2500 tok), so the embedder currently sees ~20% of each session while BM25 indexes all of it. Add chunk-level semantic retrieval so the whole session is embedded in windows and a doc scores by its best-matching chunk.

Purpose: recover semantic recall lost to head-truncation without altering the existing (reproducible) default path.
Output: `semantic_rank_chunked` in bench/_retrieval.py + `--chunk-tokens` wiring in bench/longmemeval.py + tests.

Constraints (from spec): ADD-ONLY. Touch ONLY bench/_retrieval.py, bench/longmemeval.py, and their test files. Do NOT touch bench/grounding.py, bench/locomo*.py, bench/longmemeval_qa.py, flowstate/, or pyproject.toml. never-raises. stdlib + bench only. ruff 100col / double-quotes.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@/Users/jhogan/frameworx/CLAUDE.md

<interfaces>
Existing semantic_rank pattern to mirror (bench/_retrieval.py) — DO NOT modify it:

```python
def semantic_rank(docs: list[tuple[str, str]], query: str, k: int, embed_fn) -> list[str]:
    # never-raises; on any exception -> print note + return []
    # import sqlite_vec (local); embed_fn(texts) -> list[list[float]]; embed_fn([query])[0]
    # conn.enable_load_extension(True); sqlite_vec.load(conn)
    # CREATE VIRTUAL TABLE vec_docs USING vec0(embedding float[{dim}])
    # INSERT rowid, sqlite_vec.serialize_float32(vec)
    # SELECT rowid, distance ... WHERE embedding MATCH ? ORDER BY distance LIMIT k
```

longmemeval.py ranker wiring (lines ~192-197): bm25 vs semantic lambda selection,
uses module-attribute access `_retrieval.semantic_rank(...)` so tests monkeypatch on the module.
Output dict built at lines ~184-190 (add `chunk_tokens` there).

Test idioms (tests/test_longmemeval.py): `_fake_embed_factory(keyword, match_vec, default_vec)`
returns embed_fn mapping texts containing keyword -> match_vec; `_HAS_VEC` skipif guard for sqlite_vec.
</interfaces>
</context>

<tasks>

<task type="tdd" tdd="true">
  <name>Task 1 (RED): Failing tests for semantic_rank_chunked + --chunk-tokens wiring</name>
  <files>tests/test_retrieval_chunked.py, tests/test_longmemeval.py</files>
  <behavior>
    New file tests/test_retrieval_chunked.py (import `bench._retrieval as r`; `_HAS_VEC` skipif guard; local `_fake_embed_factory` helper mirroring test_longmemeval.py):
    - test_chunking_splits_long_doc: a doc with text >> chunk_chars splits into >1 chunk on whitespace boundaries (no word cut mid-token); a short doc -> exactly 1 chunk. Assert via a helper OR indirectly by rollup behavior. Prefer exposing a private `_chunk_text(text, chunk_tokens)` in _retrieval.py and testing it directly (whitespace-split, len>1 for long, ==1 for short, no partial words).
    - test_max_sim_rollup (THE core test, skipif no vec): build two docs. Gold doc = "HEAD_FILLER... <long> ... GOLDMATCH tail" so GOLDMATCH lands in its SECOND chunk; distractor doc has no match. fake embed_fn returns match_vec ONLY for chunks/query containing "GOLDMATCH", default_vec otherwise. Assert semantic_rank_chunked(docs, "GOLDMATCH", k=1, embed_fn, chunk_tokens=<small>) == [gold_id]. Also assert plain r.semantic_rank(...) does NOT rank gold first (it embeds only the truncated whole-doc head) — proves why the fix exists.
    - test_dedup: a doc whose multiple chunks all near the query appears exactly once in results.
    - test_k_semantics: with 3+ matching docs and k=2, result length == 2.
    - test_never_raises_embed_error: embed_fn that raises -> returns [].
    - test_never_raises_no_vec (no skipif): monkeypatch to simulate missing sqlite_vec OR call with embed_fn raising -> []; assert never propagates.
    In tests/test_longmemeval.py ADD (do not alter existing tests):
    - test_chunk_tokens_zero_uses_plain_semantic: monkeypatch `_retrieval.semantic_rank` and `_retrieval.semantic_rank_chunked` with call-recorders; run main(--chunk-tokens 0 or omitted, semantic backend forced available via monkeypatched semantic_backend_available returning a fake embed_fn); assert semantic_rank called, semantic_rank_chunked NOT called; assert output JSON has chunk_tokens == 0.
    - test_chunk_tokens_positive_uses_chunked: same setup with --chunk-tokens 400; assert semantic_rank_chunked called, plain NOT; assert JSON chunk_tokens == 400.
  </behavior>
  <action>Write the failing tests per <behavior>. Reference the sqlite_vec skipif idiom and _fake_embed_factory from tests/test_longmemeval.py. For the longmemeval main() wiring tests, force the semantic arm available by monkeypatching `bench._retrieval.semantic_backend_available` to return `(fake_embed_fn, True)`. Run `ruff check --fix` on the new/edited test files yourself — the `import bench.x as y` idiom trips I001. Do NOT implement production code in this task.</action>
  <verify>
    <automated>cd /Users/jhogan/frameworx && python -m pytest tests/test_retrieval_chunked.py tests/test_longmemeval.py::test_chunk_tokens_zero_uses_plain_semantic tests/test_longmemeval.py::test_chunk_tokens_positive_uses_chunked -q 2>&1 | tail -20; ruff check tests/test_retrieval_chunked.py tests/test_longmemeval.py</automated>
  </verify>
  <done>New tests exist and FAIL (semantic_rank_chunked / --chunk-tokens not yet implemented). ruff clean on touched test files. No production code changed.</done>
</task>

<task type="tdd" tdd="true">
  <name>Task 2 (GREEN): Implement semantic_rank_chunked + --chunk-tokens wiring</name>
  <files>bench/_retrieval.py, bench/longmemeval.py</files>
  <action>
Implement to pass Task 1 tests. Per QTE-01.

bench/_retrieval.py (ADD; do NOT modify existing semantic_rank):
- Add `_chunk_text(text: str, chunk_tokens: int) -> list[str]`: chunk_chars = chunk_tokens*4; split text on whitespace into words; greedily pack words into windows so each window's char length stays near chunk_chars WITHOUT cutting a word; a text shorter than one window -> single-element list. Empty/blank text -> [] (or one empty chunk — pick so a blank doc contributes nothing).
- Add `semantic_rank_chunked(docs, query, k, embed_fn, *, chunk_tokens=400) -> list[str]`: never-raises (blank query or empty docs -> []; wrap all in try/except -> print note + []). Build flat chunk list with parallel `chunk_doc_ids` map (chunk_index -> doc_id) via `_chunk_text` over each doc. Embed ALL chunks in ONE embed_fn(all_chunks) call (batch); embed query once. Mirror semantic_rank's vec0 pattern (enable_load_extension, sqlite_vec.load, vec0 table float[dim], serialize_float32, ORDER BY distance). Over-fetch KNN (LIMIT = number of chunks, i.e. all) then MAX-SIM ROLLUP: for each returned (chunk_rowid, distance) keep the MIN distance per doc_id (best chunk). Sort unique doc_ids ascending by best-chunk distance; return first k.
- Keep imports local (import sqlite_vec inside the try) exactly like semantic_rank.

bench/longmemeval.py:
- Add argparse arg `--chunk-tokens` (type=int, default=0, help describing 0 = legacy semantic_rank).
- Add `"chunk_tokens": args.chunk_tokens` to the `output` dict (near line 184-190).
- In the semantic ranker branch (line ~195-197): if `args.chunk_tokens > 0`, build ranker calling `_retrieval.semantic_rank_chunked(docs, q, k_, __ef, chunk_tokens=args.chunk_tokens)`; else keep `_retrieval.semantic_rank(docs, q, k_, __ef)`. Use module-attribute access on `_retrieval` so tests monkeypatch on the owning module. bm25 branch unchanged.
- --chunk-tokens 0 path must stay BYTE-IDENTICAL in behavior to today (same semantic_rank call) so prior numbers reproduce.

Run `ruff check --fix` then `ruff format` on both files.
  </action>
  <verify>
    <automated>cd /Users/jhogan/frameworx && python -m pytest tests/test_retrieval_chunked.py tests/test_longmemeval.py -q 2>&1 | tail -20 && python -m pytest tests/ --cov=flowstate --cov-fail-under=80 -q 2>&1 | tail -15 && ruff check bench/_retrieval.py bench/longmemeval.py tests/test_retrieval_chunked.py tests/test_longmemeval.py && ruff format --check bench/_retrieval.py bench/longmemeval.py && git diff --name-only</automated>
  </verify>
  <done>All new + existing longmemeval tests GREEN; full suite passes with coverage >=80%; ruff check + format --check clean; `git diff --name-only` shows ONLY bench/_retrieval.py, bench/longmemeval.py, tests/test_retrieval_chunked.py, tests/test_longmemeval.py.</done>
</task>

</tasks>

<verification>
- Core proof: test_max_sim_rollup passes under semantic_rank_chunked AND demonstrates plain semantic_rank fails (second-chunk match recovered only by chunking).
- Regression: existing test_longmemeval.py tests unchanged and green; --chunk-tokens 0 == legacy path.
- Scope: git diff limited to the four allowed files; grep confirms bench/grounding.py, bench/locomo*.py, bench/longmemeval_qa.py, flowstate/, pyproject.toml untouched.
</verification>

<success_criteria>
- semantic_rank_chunked exists, never-raises, max-sim rollup + dedup + k honored.
- --chunk-tokens flag: 0 -> semantic_rank (reproducible); >0 -> semantic_rank_chunked; chunk_tokens recorded in JSON.
- Full suite green, coverage >=80%, ruff clean, diff scoped to 4 files.
</success_criteria>

<output>
Create `.planning/quick/260709-qte-add-chunk-level-semantic-retrieval-to-be/SUMMARY.md` and `.planning/quick/260709-qte-add-chunk-level-semantic-retrieval-to-be/260709-qte-SUMMARY.md` (status: complete) when done.
</output>
