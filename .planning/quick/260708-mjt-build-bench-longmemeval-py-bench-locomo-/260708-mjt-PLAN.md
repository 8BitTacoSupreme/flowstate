---
phase: quick-260708-mjt
plan: 01
type: tdd
wave: 1
depends_on: []
files_modified:
  - bench/fixtures/lme_smoke.json
  - bench/fixtures/locomo_smoke.json
  - tests/test_longmemeval.py
  - tests/test_locomo.py
  - bench/_retrieval.py
  - bench/longmemeval.py
  - bench/locomo.py
autonomous: true
requirements: [260708-mjt]
must_haves:
  truths:
    - "python -m bench.longmemeval --data bench/fixtures/lme_smoke.json --backends bm25 --k 5,10 --out /tmp/lme.json returns 0 with sane recall numbers"
    - "python -m bench.locomo --data bench/fixtures/locomo_smoke.json --backends bm25 --top-n 5 --out /tmp/loc.json returns 0 with sane coverage numbers"
    - "recall_all@k / recall_any@k compute exactly per the LongMemEval formula; a multi-gold instance with only one gold in top-k yields recall_any=1.0, recall_all=0.0"
    - "LoCoMo coverage for a qa with 2 evidence ids where 1 is retrieved == 0.5, full_coverage==0"
    - "bad/missing data file prints a note and returns 1, never raises; malformed instances are skipped and counted"
    - "semantic arm skipped with a printed note when fastembed/sqlite_vec unavailable; bm25 arm still runs"
    - "bench/grounding.py and all of flowstate/ are UNCHANGED (only new files added)"
  artifacts:
    - path: "bench/longmemeval.py"
      provides: "LongMemEval session-level Recall@k retrieval harness + main(argv)->int"
      contains: "def main"
    - path: "bench/locomo.py"
      provides: "LoCoMo evidence-coverage retrieval harness + main(argv)->int"
      contains: "def main"
    - path: "bench/_retrieval.py"
      provides: "Shared bm25/fts5 + semantic (sqlite-vec) in-memory ranking backends over (id,text) doc lists"
      contains: "def bm25_rank"
    - path: "bench/fixtures/lme_smoke.json"
      provides: "Synthetic schema-faithful LongMemEval smoke instances (incl. one multi-gold)"
    - path: "bench/fixtures/locomo_smoke.json"
      provides: "Synthetic schema-faithful LoCoMo smoke conversation(s) (incl. one 2-evidence qa)"
    - path: "tests/test_longmemeval.py"
      provides: "Offline metric-math + backend + main() tests"
    - path: "tests/test_locomo.py"
      provides: "Offline metric-math + backend + main() tests"
  key_links:
    - from: "bench/longmemeval.py"
      to: "bench.grounding"
      via: "import _sanitize_fts_query, _wilson, _default_embedder"
      pattern: "from bench.grounding import"
    - from: "bench/locomo.py"
      to: "bench._retrieval"
      via: "import bm25_rank, semantic_rank, semantic_backend_available"
      pattern: "from bench._retrieval import"
---

<objective>
Build two ADD-ONLY, deterministic, NO-LLM retrieval-evaluation harnesses that reproduce the
public LongMemEval (session-level Recall@k) and LoCoMo (evidence-coverage) retrieval metrics,
comparing FlowState's semantic backend (fastembed + sqlite-vec) against a BM25/FTS5 baseline.
Plus schema-faithful synthetic smoke fixtures and offline tests.

This is "Task A" (retrieval only). A later task adds the QA reader+judge — do NOT build it here.

Purpose: give FlowState a public-benchmark-faithful yardstick for retrieval quality, reusing the
exact FTS5 + sqlite-vec patterns already proven in bench/grounding.py.

Output: bench/_retrieval.py (shared backends), bench/longmemeval.py, bench/locomo.py, two
fixtures, two test modules. bench/grounding.py and flowstate/ untouched.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@/Users/jhogan/frameworx/CLAUDE.md

<constraints_authoritative>
The `<design_spec>` supplied by the invoking task is authoritative and quoted from the
benchmarks' official eval code. Implement the metrics EXACTLY as specified there. Key
hard constraints repeated for the executor:

- ADD-ONLY: create NEW files only. Do NOT modify bench/grounding.py or anything under flowstate/.
  Import shared helpers FROM bench.grounding (never edit it).
- never-raises: loaders and eval entry points wrap bodies in try/except and return safe
  sentinels ([] / None / 1); a bad/missing data file prints a note and returns non-zero,
  never crashes.
- stdlib + flowstate + bench.grounding imports only. NO new third-party deps. fastembed and
  sqlite_vec are OPTIONAL (semantic backend degrades/skips when absent — mirror grounding.py's
  wikivec guard).
- ruff format (line-length 100, double quotes), snake_case, `from __future__ import annotations`.
- Data files are EXTERNAL/user-provided at runtime (LongMemEval 3GB, LoCoMo CC-BY-NC). Do NOT
  download or commit any real dataset. Only the small SYNTHETIC smoke fixtures are committed.

DECISION (Claude's discretion, per design_spec allowance): implement the two retrieval backends
ONCE in a new shared module `bench/_retrieval.py` and import them into both harnesses, rather
than duplicating per module. This is DRY, keeps each harness lean, and is explicitly permitted
("implement in a small shared helper or duplicate minimally per module").
</constraints_authoritative>

<interfaces>
<!-- Reused directly from bench/grounding.py — import, do NOT reimplement, do NOT edit grounding.py. -->

From bench/grounding.py:
```python
def _sanitize_fts_query(query: str) -> str: ...          # FTS5 MATCH escaping
def _wilson(successes: int, n: int) -> tuple[float, float]: ...  # Wilson CI, n==0 -> (0.0, 0.0)
def _default_embedder(model_name: str): ...              # -> embed_fn(texts)->list[list[float]]; raises RuntimeError if fastembed missing
```

Patterns to ADAPT (study, do NOT reuse directly — they glob a directory; you need in-memory (id,text) lists):
```python
# _retrieve_wiki  (grounding.py ~L128): in-memory FTS5
#   CREATE VIRTUAL TABLE docs USING fts5(path UNINDEXED, content, tokenize='porter unicode61')
#   INSERT ...; SELECT ... WHERE docs MATCH ? ORDER BY rank LIMIT ?  (uses _sanitize_fts_query)
# _retrieve_vec   (grounding.py ~L185): sqlite-vec KNN
#   import sqlite_vec; conn.enable_load_extension(True); sqlite_vec.load(conn)
#   CREATE VIRTUAL TABLE vec_docs USING vec0(embedding float[{dim}])
#   INSERT (rowid, sqlite_vec.serialize_float32(vec)); SELECT rowid, distance ... ORDER BY distance LIMIT ?
```

Offline test idiom (from tests/test_bench_grounding.py — mirror precisely):
```python
try:
    import sqlite_vec  # noqa: F401
    _HAS_VEC = True
except Exception:
    _HAS_VEC = False

@pytest.mark.skipif(not _HAS_VEC, reason="sqlite_vec not installed")
def test_...(): ...

def _fake_embed_factory(keyword, match_vec, default_vec):
    def embed_fn(texts): return [match_vec[:] if keyword in t else default_vec[:] for t in texts]
    return embed_fn
```
</interfaces>
</context>

<tasks>

<task type="tdd" tdd="true">
  <name>Task 1: RED — smoke fixtures + failing offline tests for both harnesses</name>
  <files>bench/fixtures/lme_smoke.json, bench/fixtures/locomo_smoke.json, tests/test_longmemeval.py, tests/test_locomo.py</files>
  <behavior>
    FIXTURES (synthetic, schema-faithful, small — full schema per design_spec):
    - lme_smoke.json: 2-3 LongMemEval instances. Each instance has ~4-5 sessions; exactly one
      (listed in answer_session_ids) is clearly on-topic for `question` with keyword overlap so
      BOTH bm25 and semantic can find it; the rest are off-topic distractors. Include ONE instance
      with a 2-element answer_session_ids (multi-gold) so recall_all vs recall_any diverge in top-k.
      Every field present: question_id, question_type, question, answer, question_date,
      haystack_session_ids, haystack_dates, haystack_sessions (parallel to ids;
      each turn = {role, content, has_answer}), answer_session_ids.
    - locomo_smoke.json: 1-2 conversations, each conversation.conversation has 2-3 sessions
      (session_1, session_1_date_time, session_2, ...) with a few turns {speaker, dia_id, text}
      (dia_ids D001..). 2-4 qa items {question, answer, category, evidence:[dia_id,...]}; include
      ONE qa with 2 evidence ids. Full schema: sample_id, speaker_a, speaker_b, conversation, qa.

    TESTS — LongMemEval (tests/test_longmemeval.py):
    - Loader happy path returns a non-empty list; missing/empty/bad-json file -> None (never raises).
    - METRIC MATH (drive backend with a STUB ranking fn, no embedder/FTS needed): gold in top-k ->
      recall_all@k==1.0 and recall_any@k==1.0; gold NOT in top-k -> both 0.0; multi-gold with only
      one of two golds in top-k -> recall_any==1.0, recall_all==0.0.
    - bm25 backend on lme_smoke returns the on-topic (gold) session id within top-k (real in-memory FTS).
    - semantic backend with an INJECTED fake embed_fn (deterministic vectors making gold nearest)
      returns gold in top-k; @skipif sqlite_vec absent.
    - semantic unavailable (no embedder) -> arm skipped, bm25 still runs, main() returns 0, note printed.
    - end-to-end main(["--data", lme_smoke, "--backends", "bm25", "--k", "5,10", "--out", tmp]) -> 0;
      JSON has keys benchmark/n_instances/skipped/embed_model/backends with
      backends.bm25.recall_all["5"|"10"].{mean,n,wilson_ci} and recall_any likewise.
    - never-raises: a malformed instance in the data list is skipped/counted, no exception; abstention
      instance with empty answer_session_ids is skipped and counted in `skipped`.

    TESTS — LoCoMo (tests/test_locomo.py):
    - Loader happy + missing-file (None, never raises).
    - METRIC MATH: qa with 2 evidence ids, 1 retrieved in top-n -> coverage==0.5, full_coverage==0;
      all evidence retrieved -> coverage==1.0, full_coverage==1; empty-evidence qa skipped and counted.
    - bm25 backend on locomo_smoke returns the gold dia_id(s) for an on-topic qa within top-n.
    - semantic backend with injected fake embed_fn returns gold dia_id in top-n; @skipif sqlite_vec absent.
    - semantic unavailable -> arm skipped, bm25 still runs, main() -> 0, note printed.
    - end-to-end main(["--data", locomo_smoke, "--backends", "bm25", "--top-n", "5", "--out", tmp]) -> 0;
      JSON keys benchmark/n_qa/skipped/top_n/embed_model/backends with
      backends.bm25.{mean_coverage, full_coverage_rate, wilson_ci, n}.
  </behavior>
  <action>
    Author the two JSON fixtures per the schemas above (mirror bench/fixtures/rgb_probes.example.json
    JSON style — 2-space indent, Kafka/Confluent-flavored content is fine and keeps keyword overlap
    easy to reason about). Then write both test modules mirroring tests/test_bench_grounding.py's
    offline idiom exactly: `import bench.longmemeval as lme` / `import bench.locomo as loc`, use the
    `_HAS_VEC` skipif guard and a `_fake_embed_factory` helper, monkeypatch where needed, and use
    tmp_path for --out. The metric-math tests MUST call the harness's metric/aggregation functions
    directly with a stub ranked-id list (do not go through a real backend) so they need neither
    fastembed nor sqlite_vec. Tests will FAIL now because the target modules do not yet exist — that
    is the RED gate. Do NOT touch bench/grounding.py or flowstate/.
  </action>
  <verify>
    <automated>cd /Users/jhogan/frameworx && python -m pytest tests/test_longmemeval.py tests/test_locomo.py -q 2>&1 | grep -Eiq 'error|no module|failed|collected' && echo RED_OK</automated>
  </verify>
  <done>Both fixtures exist with full schemas (incl. a multi-gold LME instance and a 2-evidence LoCoMo qa); both test modules exist and FAIL only due to the not-yet-created target modules (collection/import errors or assertion failures), not due to test bugs.</done>
</task>

<task type="tdd" tdd="true">
  <name>Task 2: GREEN — bench/_retrieval.py shared backends + bench/longmemeval.py</name>
  <files>bench/_retrieval.py, bench/longmemeval.py</files>
  <behavior>
    bench/_retrieval.py (shared, never-raises, `from __future__ import annotations`):
    - `bm25_rank(docs: list[tuple[str, str]], query: str, k: int) -> list[str]`: build an in-memory
      FTS5 table (id UNINDEXED, content, tokenize='porter unicode61'), insert docs, MATCH the
      _sanitize_fts_query(query) ORDER BY rank LIMIT k, return the ranked ids most-relevant-first.
      Blank/empty query or empty docs -> []; any exception caught -> print note + [].
    - `semantic_rank(docs, query, k, embed_fn) -> list[str]`: embed all doc texts + query via embed_fn,
      in-memory sqlite-vec vec0 KNN (enable_load_extension, sqlite_vec.load, vec0(embedding float[dim]),
      insert serialized vectors keyed by rowid, ORDER BY distance LIMIT k), map rowids back to ids.
      Import sqlite_vec locally inside the try; any exception (incl. sqlite_vec/embed_fn failure)
      -> print note + []. Never raises.
    - `semantic_backend_available(embed_model: str) -> tuple[embed_fn | None, bool]` (or equivalent):
      try `_default_embedder(embed_model)` AND `import sqlite_vec`; on any failure return (None, False)
      and let the caller print a skip note. Mirrors grounding.py's wikivec guard.
    Import `_sanitize_fts_query`, `_default_embedder` from bench.grounding.

    bench/longmemeval.py (never-raises throughout; `from __future__ import annotations`):
    - `_load_data(path) -> list[dict] | None`: json.loads, require non-empty list, else None. Never raises.
    - Corpus builder: for one instance, docs = list of (session_id, session_text) where session_text
      joins turns as "{role}: {content}" lines; ids come from haystack_session_ids (parallel to
      haystack_sessions). Guard against ragged/missing lists (skip malformed instance).
    - Per-instance metric: given ranked_ids and gold=answer_session_ids and k:
        recalled = set(ranked_ids[:k])
        recall_any = 1.0 if any(g in recalled for g in gold) else 0.0
        recall_all = 1.0 if all(g in recalled for g in gold) else 0.0
      Skip instances with empty answer_session_ids (count into `skipped`).
    - Aggregation: for each backend and each metric in {recall_all, recall_any} and each k, mean over
      instances + Wilson CI via _wilson(successes=count of 1.0, n=n_instances). Keep a seam so the
      metric/aggregation is unit-testable with a stub ranked-id list (a small pure function taking a
      ranker callable).
    - CLI (argparse, main(argv)->int): --data (required), --backends semantic,bm25 (default both),
      --k 5,10, --embed-model BAAI/bge-small-en-v1.5, --out <json>, --limit <n> (optional cap).
      Load data (None -> print note + return 1). For each requested+available backend, run over all
      (limited) instances at max(ks), aggregate, write JSON (never-raises around write), print a
      grounding.py-style console summary table. Semantic arm: use semantic_backend_available; if
      unavailable, print a note and drop it, still run bm25.
    - JSON: {"benchmark":"longmemeval","n_instances","skipped","embed_model","backends":
      {"bm25":{"recall_all":{"5":{"mean","n","wilson_ci"},"10":{...}},"recall_any":{...}},"semantic":{...}}}
  </behavior>
  <action>
    Implement bench/_retrieval.py first (both backends + availability probe), then bench/longmemeval.py
    importing from it and from bench.grounding. Adapt the FTS5/vec patterns from grounding.py's
    _retrieve_wiki/_retrieve_vec to operate on in-memory (id,text) lists and return ids. Keep the
    per-instance metric and aggregation as small pure functions so Task 1's metric-math tests hit them
    directly. Run each backend once per instance at k=max(--k) then slice for each k. Console table in
    the grounding.py visual style (header + dashes + per-row mean/CI/n). Do NOT modify grounding.py or
    flowstate/. Run ruff format on the new files.
  </action>
  <verify>
    <automated>cd /Users/jhogan/frameworx && python -m pytest tests/test_longmemeval.py -q && python -m bench.longmemeval --data bench/fixtures/lme_smoke.json --backends bm25 --k 5,10 --out /tmp/lme.json && python -c "import json;d=json.load(open('/tmp/lme.json'));assert d['benchmark']=='longmemeval';assert 'recall_all' in d['backends']['bm25'] and 'recall_any' in d['backends']['bm25'];print('LME_OK')"
