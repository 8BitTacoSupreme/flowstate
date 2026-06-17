---
phase: quick-260617-oos
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - bench/grounding.py
  - tests/test_bench_grounding.py
autonomous: true
requirements: [WIKIVEC-01]
must_haves:
  truths:
    - "bench.grounding imports cleanly WITHOUT fastembed installed (lazy import inside _default_embedder only)"
    - "_retrieve_vec returns the semantically-closest doc first (per injected fake embed_fn), len<=k, never raises"
    - "sqlite_vec.load + vec0 + serialize_float32 wiring works in-process with fake vectors"
    - "wikivec arm records `retrieved` paths and does NOT call build_context_prefix"
    - "wikivec with no --wiki-dir prints a clear message and makes zero answer/judge subprocess calls"
    - "_default_embedder raises a clear RuntimeError when fastembed import fails; arm degrades gracefully (skipped, no crash)"
    - "Full suite green at >=80% coverage; ruff check + format --check pass"
  artifacts:
    - path: "bench/grounding.py"
      provides: "_default_embedder, _retrieve_vec, wikivec arm branch, --embed-model CLI arg, embed_model in output JSON"
      contains: "_retrieve_vec"
    - path: "tests/test_bench_grounding.py"
      provides: "wikivec tests with injected fake embed_fn; LLM mocked; sqlite_vec graceful skip"
      contains: "wikivec"
  key_links:
    - from: "bench/grounding.py main()"
      to: "_retrieve_vec"
      via: "arm == 'wikivec' branch before _LAYERS_MAP lookup"
      pattern: "arm == .wikivec."
    - from: "_retrieve_vec"
      to: "sqlite_vec.serialize_float32 + vec0 MATCH"
      via: "in-memory sqlite3 conn with sqlite_vec.load"
      pattern: "serialize_float32"
---

<objective>
Add a `wikivec` semantic-retrieval arm to bench/grounding.py: per-probe sqlite-vec KNN over fastembed
embeddings of the wiki articles, to test whether semantic retrieval recovers the grounding lift that the
BM25 `wikirag` arm lost (BM25 surfaced the correct article in only 3/20 probes).

Purpose: Lexical density != fact location. Semantic embeddings (BAAI/bge-small-en-v1.5, 384-dim) should
locate the right article where BM25 failed. This adds a third retrieval arm alongside `wikirag` (BM25) and
`wiki` (hand-placed oracle).

Output: ADD-ONLY changes to bench/grounding.py and tests/test_bench_grounding.py. No pyproject/uv.lock
changes — fastembed stays a bench-only optional dep, imported lazily ONLY inside _default_embedder.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@CLAUDE.md
@.claude/CLAUDE.md

@bench/grounding.py
@tests/test_bench_grounding.py

<interfaces>
<!-- Existing seams in bench/grounding.py the new arm mirrors. Use these directly; no exploration needed. -->

Existing retrieval helper (mirror its never-raises shape and (path, content) return):
  def _retrieve_wiki(wiki_dir: Path, query: str, k: int) -> list[tuple[str, str]]
    - glob "**/*.md" via sorted(wiki_dir.glob(...)); read_text(errors="ignore"); skip on per-file Exception
    - returns [] on missing/not-a-dir, blank query, or any top-level Exception (prints "note: ...")

Existing CLI (bench/grounding.py:209-226):
  --layers choices=("full","none","pack","memory","wiki","wikirag"), default=["none","pack","wiki"]
  --wiki-dir (Path, default None), --rag-k (int, default 3), --budget-tokens (int, default 50000)

Existing arm dispatch (bench/grounding.py:257-299), per (trial, arm, probe):
  - wikirag guard BEFORE probe loop: `if arm == "wikirag" and args.wiki_dir is None: print(...); continue`
  - wikirag branch: hits = _retrieve_wiki(...); prefix = ("\n\n---\n\n".join(content for _,content in hits))[:budget_chars]; retrieved = [path for path,_ in hits]
  - else branch: build_context_prefix(root, mem, query=..., include_layers=_LAYERS_MAP[arm]); retrieved = []
  - budget_chars = args.budget_tokens * 4 (already computed at line 252)
  - answer = _answer(prefix, probe["question"], args.answer_model); votes via _factcheck; per-probe record carries "retrieved"

Existing output dict (bench/grounding.py:327-335): probes_file, n_probes, trials, answer_model, judge_models, arms, accuracy_delta_vs_none
Zero-records guard (line 302): `if all(len(v)==0 for v in arm_records.values()): return 1`

sqlite_vec API (confirmed v0.1.9 in .venv):
  import sqlite_vec
  conn.enable_load_extension(True); sqlite_vec.load(conn)
  CREATE VIRTUAL TABLE vec_docs USING vec0(embedding float[<dim>])
  INSERT INTO vec_docs(rowid, embedding) VALUES (?, ?)  -- with sqlite_vec.serialize_float32(vec)
  SELECT rowid, distance FROM vec_docs WHERE embedding MATCH ? ORDER BY distance LIMIT ?

fastembed API (confirmed present in .venv; LAZY import only):
  from fastembed import TextEmbedding
  model = TextEmbedding(model_name)          # construct once
  list(model.embed(texts))                   # generator of numpy arrays -> convert each to list[float]
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Add _default_embedder + _retrieve_vec + wikivec arm wiring</name>
  <files>bench/grounding.py</files>
  <behavior>
    - _default_embedder(model_name) returns a callable embed_fn(texts)->list[list[float]]; lazily `from fastembed import TextEmbedding` inside the function; constructs model once; converts each vector to a python list of floats. On import failure raises RuntimeError with a clear message (caller catches).
    - _retrieve_vec(wiki_dir, query, k, embed_fn) returns up to k (path, content) most-similar-first; [] on missing/empty dir, blank query, or any exception (never raises; prints a note).
    - With an injected fake embed_fn over a tiny corpus, the semantically-closest doc comes first; len<=k.
    - wikivec arm: records `retrieved` paths, does NOT call build_context_prefix; with no --wiki-dir prints clear message and skips (or rc!=0 if only arm).
  </behavior>
  <action>
    Edit bench/grounding.py (ADD-ONLY; do not change existing functions' behavior).

    (a) Module docstring: append a sentence noting fastembed is a bench-only OPTIONAL dep
    (`pip install fastembed`), lazily imported inside _default_embedder, used ONLY by the wikivec arm;
    importing bench.grounding must work without it.

    (b) Add `_default_embedder(model_name: str)` near the FTS5 helpers section. It builds and returns a
    closure embed_fn. Inside _default_embedder: `try: from fastembed import TextEmbedding` / construct
    `model = TextEmbedding(model_name)` once; `except Exception as exc: raise RuntimeError("fastembed is
    required for the wikivec arm (pip install fastembed): " + str(exc)) from exc`. The returned
    `embed_fn(texts: list[str]) -> list[list[float]]` calls `list(model.embed(texts))` and converts each
    vector to a list of floats via `[float(x) for x in vec]` (handles numpy arrays). Do NOT import
    fastembed at module top level.

    (c) Add `_retrieve_vec(wiki_dir: Path, query: str, k: int, embed_fn) -> list[tuple[str, str]]`
    mirroring _retrieve_wiki's never-raises shape. Steps inside a single top-level try/except (on
    Exception: `print(f"note: wikivec retrieval failed: {exc}")`; return []):
      - if not wiki_dir or not wiki_dir.is_dir(): return []
      - if not query.strip(): return []
      - Collect docs: for p in sorted(wiki_dir.glob("**/*.md")): read_text(errors="ignore"); skip empties
        (text.strip()=="") and per-file read errors (continue); keep parallel lists paths[], contents[].
      - if not contents: return []
      - vectors = embed_fn(contents); qvec = embed_fn([query])[0]; dim = len(qvec).
      - conn = sqlite3.connect(":memory:"); conn.enable_load_extension(True);
        `import sqlite_vec` (local import — already a runtime dep); sqlite_vec.load(conn).
      - conn.execute(f"CREATE VIRTUAL TABLE vec_docs USING vec0(embedding float[{dim}])").
      - for i, vec in enumerate(vectors): conn.execute("INSERT INTO vec_docs(rowid, embedding) VALUES (?, ?)",
        (i, sqlite_vec.serialize_float32(vec))).  (i is the rowid -> maps to paths[i]/contents[i].)
      - rows = conn.execute("SELECT rowid, distance FROM vec_docs WHERE embedding MATCH ? ORDER BY distance
        LIMIT ?", (sqlite_vec.serialize_float32(qvec), k)).fetchall(); conn.close() in finally.
      - return [(paths[r[0]], contents[r[0]]) for r in rows]  (already distance-asc).

    (d) CLI (_build_parser): add `"wikivec"` to the --layers choices tuple. Add
    `parser.add_argument("--embed-model", default="BAAI/bge-small-en-v1.5")`. Reuse existing --wiki-dir
    and --rag-k.

    (e) main(): build the default embedder ONCE, only when wikivec is requested, BEFORE the trial loop:
      `embed_fn = None`
      `if "wikivec" in args.layers and args.wiki_dir is not None:`
      `    try: embed_fn = _default_embedder(args.embed_model)`
      `    except Exception as exc: print(f"wikivec arm unavailable: {exc}")`  (embed_fn stays None)

    (f) main() arm dispatch — add a wikivec guard alongside the existing wikirag guard (before the probe
    loop): `if arm == "wikivec" and (args.wiki_dir is None or embed_fn is None): print("wikivec arm
    requires --wiki-dir and fastembed; skipping"); continue`. Then add a wikivec branch BEFORE the
    _LAYERS_MAP lookup, parallel to wikirag:
      `elif arm == "wikivec":`
      `    hits = _retrieve_vec(args.wiki_dir, probe["question"], args.rag_k, embed_fn)`
      `    prefix = ("\n\n---\n\n".join(content for _, content in hits))[:budget_chars]`
      `    retrieved = [path for path, _ in hits]`
    Do NOT call build_context_prefix for wikivec. Everything after (answer/_factcheck/votes/per-probe
    record) is shared with other arms — leave it untouched.

    (g) Output JSON: add `"embed_model": args.embed_model` to the `output` dict (alongside answer_model).

    Keep ruff happy: line-length 100, double quotes, no unused imports. The existing zero-records guard
    (return 1) already covers the wikivec-only-without-dir case.
  </action>
  <verify>
    <automated>cd /Users/jhogan/frameworx && .venv/bin/python -c "import bench.grounding as g; assert hasattr(g,'_retrieve_vec') and hasattr(g,'_default_embedder'); assert 'wikivec' in str(g._build_parser()._actions)" && .venv/bin/python -m ruff check bench/grounding.py</automated>
  </verify>
  <done>bench.grounding imports without fastembed at top level; _default_embedder and _retrieve_vec exist; --embed-model and wikivec choice present; wikivec branch records retrieved and skips build_context_prefix; embed_model in output; ruff clean.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Tests for wikivec arm with injected fake embedder (no fastembed/network)</name>
  <files>tests/test_bench_grounding.py</files>
  <behavior>
    - _retrieve_vec with a deterministic fake embed_fn over a tiny temp corpus returns the closest doc first, len<=k; empty/missing dir -> []; never raises.
    - sqlite_vec wiring exercised in-process with fake vectors; xfail/skip gracefully if sqlite_vec import unavailable.
    - wikivec arm: monkeypatched _retrieve_vec + mocked answer/judge -> per_probe carries `retrieved` + majority; build_context_prefix NOT called.
    - wikivec with no --wiki-dir -> clear message, zero answer/judge subprocess calls, never crashes.
    - _default_embedder raises clear RuntimeError when fastembed import fails (simulated); arm degrades gracefully.
  </behavior>
  <action>
    Append tests to tests/test_bench_grounding.py mirroring the existing style (real temp corpora for
    retrieval; LLM/subprocess mocked; reuse _bcp and _Mem stubs already in the file; `import bench.grounding
    as g`). Do NOT require fastembed or any model/network — inject a fake embed_fn.

    Add a module-level skip guard for sqlite_vec at the top of the new test section:
      `import pytest`
      `try: import sqlite_vec  # noqa: F401` / `_HAS_VEC = True` / `except Exception: _HAS_VEC = False`
    and decorate the sqlite_vec-dependent tests with
      `@pytest.mark.skipif(not _HAS_VEC, reason="sqlite_vec not installed")`.
    (sqlite_vec IS installed in this .venv — confirmed v0.1.9 — so these run; the guard only protects
    foreign envs.)

    Define a deterministic fake embedder factory in the test module, e.g.
    `def _fake_embed_factory(keyword_to_vec): def embed_fn(texts): return [<vector chosen by which keyword
    appears in each text, else a far-away default>] ...`. Use small fixed-dim vectors (e.g. dim=4) so the
    closest-by-L2 doc is unambiguous. Make the query map to the same vector as the target doc and a
    distinct/far vector for distractors so KNN ordering is deterministic.

    Tests to add (each with the same `def test_...(tmp_path: Path)` / monkeypatch signatures as existing):
      1. test_retrieve_vec_ranks_semantic_match_first — write 3 .md docs (compliance/producer/consumer),
         fake embed_fn maps a compliance-flavored query + the compliance doc to the same vector; assert
         results[0] is the compliance doc path and len(results) <= k. (skipif not _HAS_VEC)
      2. test_retrieve_vec_respects_k — >k docs; assert len(results) == k. (skipif not _HAS_VEC)
      3. test_retrieve_vec_missing_and_empty_dir — missing dir -> []; empty dir -> []; blank query -> [].
         (no sqlite needed; keep un-skipped so it always runs)
      4. test_retrieve_vec_never_raises_on_bad_embed_fn — embed_fn that raises -> returns [] (not an
         exception). (no skipif)
      5. test_wikivec_arm_records_retrieved_and_skips_bcp — monkeypatch g._retrieve_vec to return known
         [(path, content)]; monkeypatch g._default_embedder to return a dummy callable (so main builds
         embed_fn without fastembed); MagicMock build_context_prefix; monkeypatch g._answer-> "ans",
         g._factcheck-> True; run main(["--root",..,"--probes",..,"--layers","wikivec","--wiki-dir",
         str(tmp_path),"--trials","1","--out",out]); assert per_probe[0]["retrieved"] == ["/w/x.md"],
         majority True, and build_context_prefix.call_count == 0. Also assert output JSON has "embed_model".
      6. test_wikivec_no_dir_clear_message_no_subprocess — layers=["wikivec"] with NO --wiki-dir;
         monkeypatch subprocess.run to a MagicMock; assert rc != 0 (only arm, zero records), run_mock not
         called, and capsys output mentions "wiki-dir". (mirror test_wikirag_no_dir_*)
      7. test_default_embedder_raises_when_fastembed_missing — simulate import failure by monkeypatching
         builtins.__import__ to raise ImportError for "fastembed" (or sys.modules["fastembed"]=None);
         assert g._default_embedder("any-model") raises RuntimeError. Then a graceful-degrade check: with
         _default_embedder monkeypatched to raise, run main with layers including wikivec + a second arm
         ("none") + --wiki-dir; assert harness does NOT crash (rc == 0 because "none" arm produces
         records) and capsys mentions "wikivec arm unavailable".

    Keep all subprocess/_answer/_factcheck mocked so no live claude is invoked. Match existing assertion
    style (read --out JSON, index arms["wikivec"]["per_probe"]).
  </action>
  <verify>
    <automated>cd /Users/jhogan/frameworx && .venv/bin/python -m pytest tests/test_bench_grounding.py -q && .venv/bin/python -m pytest tests/ --cov=flowstate --cov-fail-under=80 -q && .venv/bin/python -m ruff check flowstate/ bench/ tests/ && .venv/bin/python -m ruff format --check flowstate/ bench/ tests/</automated>
  </verify>
  <done>All new wikivec tests pass; existing grounding + wikirag tests unchanged and green; full suite >=80% coverage; ruff check + format --check clean; no fastembed import at module load; LLM/subprocess fully mocked in tests.</done>
</task>

</tasks>

<verification>
- `.venv/bin/python -c "import bench.grounding"` succeeds with NO fastembed at module level.
- `.venv/bin/python -m pytest tests/ --cov=flowstate --cov-fail-under=80` exits 0.
- `.venv/bin/python -m ruff check flowstate/ bench/ tests/` and `ruff format --check` pass.
- Only bench/grounding.py and tests/test_bench_grounding.py changed; pyproject.toml and uv.lock untouched
  (`git diff --name-only` shows exactly those two files).
</verification>

<success_criteria>
- wikivec arm added: --embed-model CLI, "wikivec" in --layers, _default_embedder (lazy fastembed),
  _retrieve_vec (sqlite-vec KNN over fastembed embeddings), wikivec branch before _LAYERS_MAP,
  embed_model in output JSON.
- _retrieve_vec returns semantically-closest doc first via injected fake embed_fn, len<=k, never raises;
  build_context_prefix NOT called for wikivec.
- No --wiki-dir or missing fastembed -> clear message, arm skipped, no crash, no answer/judge subprocess calls.
- _default_embedder raises clear RuntimeError on fastembed import failure; arm degrades gracefully.
- Tests require neither fastembed nor network; sqlite_vec-dependent tests skip gracefully if absent.
- Existing tests unchanged and green; full suite >=80%; ruff clean.
</success_criteria>

<output>
Create `.planning/quick/260617-oos-add-wikivec-semantic-retrieval-arm-sqlit/SUMMARY.md` and
`.planning/quick/260617-oos-add-wikivec-semantic-retrieval-arm-sqlit/260617-oos-SUMMARY.md` when done
(status: complete). Use atomic commits: one for Task 1 (source), one for Task 2 (tests).
</output>
