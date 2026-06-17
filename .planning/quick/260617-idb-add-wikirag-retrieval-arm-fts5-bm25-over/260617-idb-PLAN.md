---
phase: quick-260617-idb
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - bench/grounding.py
  - tests/test_bench_grounding.py
autonomous: true
requirements:
  - QUICK-260617-idb
must_haves:
  truths:
    - "A `wikirag` arm runs per-probe BM25/FTS5 retrieval over a wiki dir and answers + multi-judge fact-checks like every other arm."
    - "_retrieve_wiki returns the most-relevant doc first, capped at k, and never raises (missing/empty dir or nonsense query -> [])."
    - "FTS5-special query chars (quotes, punctuation, AND/OR barewords) are sanitized and do not raise."
    - "wikirag with no --wiki-dir prints a clear message and makes zero answer/judge subprocess calls."
    - "build_context_prefix is NOT called for the wikirag arm."
    - "Per-probe records for wikirag include a `retrieved` list of article paths."
    - "Existing none/pack/wiki arm behavior is unchanged; full suite + coverage + ruff pass."
  artifacts:
    - path: "bench/grounding.py"
      provides: "_retrieve_wiki, _sanitize_fts_query, --wiki-dir/--rag-k CLI args, wikirag choice, wikirag arm branch"
      contains: "def _retrieve_wiki"
    - path: "tests/test_bench_grounding.py"
      provides: "retrieval + sanitizer + wikirag-arm + no-wiki-dir guard tests using real temp FTS5 corpus and mocked subprocess"
      contains: "def test_retrieve_wiki"
  key_links:
    - from: "bench/grounding.py:main wikirag branch"
      to: "_retrieve_wiki"
      via: "per-probe call hits = _retrieve_wiki(wiki_dir, probe['question'], rag_k)"
      pattern: "_retrieve_wiki\\("
    - from: "bench/grounding.py:_retrieve_wiki"
      to: "sqlite3 FTS5 docs table"
      via: "MATCH ? ORDER BY rank LIMIT ?"
      pattern: "docs MATCH \\? ORDER BY rank"
---

<objective>
Add a per-probe RETRIEVAL arm `wikirag` to `bench/grounding.py`: for each probe, run BM25/FTS5
retrieval of top-k `.md` articles from a wiki directory, concatenate them into the context
prefix, then answer + multi-judge fact-check exactly like the existing arms. This tests whether
the prior grounding lift (wiki 0.825 vs none 0.050, measured with a HAND-PLACED wiki.md) survives
real retrieval over the full wiki.

Purpose: distinguish "grounding helps when you hand it the right article" from "grounding helps
when BM25 must find the right article" — the realistic case.
Output: extended `bench/grounding.py` and `tests/test_bench_grounding.py`. ADD-ONLY. No other
module is touched. Stdlib only (sqlite3, math, json, subprocess, argparse, re, pathlib).
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@bench/grounding.py
@tests/test_bench_grounding.py

<interfaces>
<!-- Existing grounding.py contracts the executor must reuse verbatim. -->

Module imports already present (bench/grounding.py top):
  argparse, json, math, os, re, subprocess, sys, from pathlib import Path
  from bench.compound_eval import _LAYERS_MAP
  from bench.judge import _locate_claude
  from flowstate.context_prefix import build_context_prefix
  from flowstate.memory import MemoryStore

Reuse these unchanged:
  _answer(prefix: str, question: str, model: str) -> str        # never-raises, retries
  _factcheck(answer: str, ground_truth: str, model: str) -> bool | None
  _wilson(successes: int, n: int) -> tuple[float, float]
  _load_probes(path: Path) -> list[dict] | None

Existing main() per-(trial,arm,probe) loop body (lines ~196-223): builds prefix via
build_context_prefix(root, mem, query=probe["question"], include_layers=_LAYERS_MAP[arm]),
then answer = _answer(...), votes = [_factcheck(...)], majority = yes > len(judge_models)/2,
appends a per-probe dict to arm_records[arm]. budget_tokens is in args.budget_tokens.

Parser (lines ~152-167): --layers has choices=("full","none","pack","memory","wiki"),
default ["none","pack","wiki"].

FTS5 mirror points from flowstate/memory.py:
  Schema idiom: CREATE VIRTUAL TABLE ... USING fts5(..., tokenize='porter unicode61')   (~line 42)
  _sanitize_fts_query (~line 220): splits on whitespace, wraps each token as '"token"'
    to force literal matching and avoid column-name / AND/OR/NEAR interpretation; empty -> query.
  Search query idiom (~line 250): WHERE <table> MATCH ? ORDER BY rank LIMIT ?  (rank == bm25)
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Add _sanitize_fts_query, _retrieve_wiki, CLI args, and the wikirag arm branch to grounding.py</name>
  <files>bench/grounding.py</files>
  <behavior>
    - _retrieve_wiki(temp_dir_with_3_md, "<term-unique-to-doc-B>", k=3) returns doc B first, len <= 3.
    - _retrieve_wiki(Path("/does/not/exist"), "q", 3) -> [] (no raise).
    - _retrieve_wiki(empty_dir, "q", 3) -> [].
    - _retrieve_wiki(dir, "", 3) -> [] or <=k, never raises.
    - _sanitize_fts_query('foo "bar" AND baz!') does not raise and yields a MATCH-safe string.
    - main with --layers wikirag and a valid --wiki-dir: per-probe record has "retrieved" list;
      build_context_prefix is NOT called for that arm.
    - main with --layers wikirag and NO --wiki-dir: prints a clear message, returns non-zero
      (wikirag is the only arm), zero _answer/_factcheck calls.
  </behavior>
  <action>
    Add a module-level `import sqlite3` (alphabetical, after `re`/before `subprocess` per ruff isort).

    Add `_sanitize_fts_query(query: str) -> str` MIRRORING flowstate/memory.py:_sanitize_fts_query
    exactly — split on whitespace; if no tokens return `query`; else return
    `" ".join(f'"{t}"' for t in tokens)`. Strip embedded double-quotes from each token before
    wrapping (replace `"` with empty) so a query like `'bar"` cannot break out of the quoted
    FTS5 string. Keep the docstring explaining the column-name / AND/OR/NEAR rationale.

    Add `_retrieve_wiki(wiki_dir: Path, query: str, k: int) -> list[tuple[str, str]]` returning
    up to k (path, content) pairs, most-relevant first. NEVER raises — wrap the whole body in
    try/except Exception and on any exception `print(f"note: wiki retrieval failed: {exc}")`
    and `return []`. Implementation:
      - If `not wiki_dir or not wiki_dir.is_dir()`: return [].
      - `safe = _sanitize_fts_query(query)`; if not safe.strip(): return [].
      - `conn = sqlite3.connect(":memory:")`; create table:
        `CREATE VIRTUAL TABLE docs USING fts5(path UNINDEXED, content, tokenize='porter unicode61')`.
      - For each `p in sorted(wiki_dir.glob("**/*.md"))`: read with
        `p.read_text(errors="ignore")` and INSERT `(str(p), text)`. Skip files that fail to read
        (per-file try/except continue) so one bad file does not abort the corpus.
      - `rows = conn.execute("SELECT path, content FROM docs WHERE docs MATCH ? ORDER BY rank LIMIT ?", (safe, k)).fetchall()`.
      - `conn.close()` (in a finally or before return); return `[(r[0], r[1]) for r in rows]`.

    Parser changes in `_build_parser`:
      - Add `"wikirag"` to the `--layers` choices tuple (append after `"wiki"`).
      - `parser.add_argument("--wiki-dir", type=Path, default=None)`.
      - `parser.add_argument("--rag-k", type=int, default=3)`.

    main() changes — special-case `arm == "wikirag"` BEFORE the `_LAYERS_MAP[arm]` lookup so the
    map is never indexed with "wikirag". Compute once near the top of main (after probes load):
    `budget_chars = args.budget_tokens * 4`. In the per-(trial,arm,probe) loop:
      - Guard, evaluated once before the probe loop or at arm entry: if arm == "wikirag" and
        (args.wiki_dir is None): print a clear message
        ("wikirag arm requires --wiki-dir; skipping" — and if wikirag is the ONLY arm, this means
        no records are produced). Skip all probe work for this arm. Implement by `continue`-ing the
        arm loop. Ensure the final guard: if after the loops `all(len(v) == 0 for v in arm_records.values())`
        because the only requested arm was wikirag-without-dir, `return 1` instead of 0 (place this
        check just before the aggregation block; it is a no-op for normal runs).
      - If arm == "wikirag" (and wiki_dir present): do NOT open MemoryStore and do NOT call
        build_context_prefix. Instead:
          `hits = _retrieve_wiki(args.wiki_dir, probe["question"], args.rag_k)`
          `prefix = ("\n\n---\n\n".join(content for _, content in hits))[:budget_chars]`
          `retrieved = [path for path, _ in hits]`
      - Else (existing arms): unchanged MemoryStore + build_context_prefix path; `retrieved = []`.
      - Then answer/votes/majority are IDENTICAL to the existing code (reuse _answer/_factcheck).
      - Append `"retrieved": retrieved` to the per-probe record dict for ALL arms (existing arms
        get `[]`), so the JSON shape is consistent.

    Do NOT change aggregation, _wilson usage, accuracy_delta_vs_none, JSON output keys, or the
    console table. wikirag participates in arm_records like any other arm.
    Keep never-raises and stdlib-only discipline throughout. No fenced code in this file beyond
    normal Python.
  </action>
  <verify>
    <automated>.venv/bin/python -c "import ast,sys; ast.parse(open('bench/grounding.py').read()); src=open('bench/grounding.py').read(); assert 'def _retrieve_wiki' in src and 'def _sanitize_fts_query' in src and \"'wikirag'\" in src.replace('\"','\\'') or 'wikirag' in src; assert 'docs MATCH ? ORDER BY rank' in src; assert 'tokenize=' in src; print('OK')"</automated>
  </verify>
  <acceptance_criteria>
    - `_retrieve_wiki` and `_sanitize_fts_query` exist; `import sqlite3` present.
    - `--wiki-dir`, `--rag-k` parse; `wikirag` is an allowed `--layers` choice.
    - wikirag branch calls `_retrieve_wiki` and never `build_context_prefix`/`MemoryStore`.
    - Every per-probe record (all arms) carries a `retrieved` key.
    - `.venv/bin/python -m ruff check bench/grounding.py` is clean.
  </acceptance_criteria>
  <done>grounding.py extended ADD-ONLY with retrieval helper, sanitizer, CLI args, and wikirag arm branch; parses and ruff-clean.</done>
</task>

<task type="auto">
  <name>Task 2: Add wikirag tests to test_bench_grounding.py (real temp FTS5 corpus; mocked subprocess)</name>
  <files>tests/test_bench_grounding.py</files>
  <action>
    ADD new tests mirroring the existing mocked-subprocess style (`import bench.grounding as g`,
    `monkeypatch`, `tmp_path`, the `_Mem` stub, `MagicMock`). Do NOT modify existing tests.
    Retrieval tests use a REAL temp corpus (sqlite FTS5 is stdlib — fine in tests); no subprocess.

    test_retrieve_wiki_ranks_match_first(tmp_path): create 3 files — a.md "apples and oranges in
    a fruit basket", b.md "the quantum chromodynamics gluon lagrangian", c.md "weather forecast
    rain tomorrow". Call `g._retrieve_wiki(tmp_path, "gluon chromodynamics", 3)`; assert results
    non-empty, `len(results) <= 3`, and `results[0][0].endswith("b.md")`.

    test_retrieve_wiki_respects_k(tmp_path): create 5 .md files all containing "common"; call with
    k=2; assert `len(results) <= 2`.

    test_retrieve_wiki_missing_and_empty_dir(tmp_path): `g._retrieve_wiki(tmp_path / "nope", "q", 3) == []`;
    make an empty dir and assert `g._retrieve_wiki(empty, "q", 3) == []`.

    test_retrieve_wiki_nonsense_query_never_raises(tmp_path): one .md file; call with
    `'foo "bar" AND baz! OR (qux)'` and with `""`; assert each returns a list with `len <= 3`
    and no exception.

    test_sanitize_fts_query_handles_special_chars(): assert
    `g._sanitize_fts_query('foo "bar" AND baz!')` returns a str and does not raise; build a tiny
    in-memory FTS5 table inside the test, insert a row, and confirm `MATCH` with the sanitized
    string executes without an sqlite OperationalError (mirror memory.py escaping behavior).

    test_wikirag_arm_records_retrieved_and_skips_bcp(monkeypatch, tmp_path): monkeypatch
    `g._retrieve_wiki` to return `[("/w/article1.md", "ctx body")]`; monkeypatch `g.build_context_prefix`
    to a MagicMock; monkeypatch `g._answer` -> "ans" and `g._factcheck` -> True; write a 1-probe
    probes.json; create a real `--wiki-dir` dir (can be empty since _retrieve_wiki is mocked).
    Call `g.main(["--root",..., "--probes",..., "--layers","wikirag","--wiki-dir",<dir>,
    "--trials","1","--judge-models","m1","--out",<out>])`. Assert rc==0; load out.json; assert
    `data["arms"]["wikirag"]["per_probe"][0]["retrieved"] == ["/w/article1.md"]`; assert the
    per_probe record reflects a majority verdict (majority True); assert the build_context_prefix
    MagicMock was NOT called.

    test_wikirag_no_dir_clear_message_no_subprocess(monkeypatch, tmp_path, capsys): set
    `subprocess.run` to a MagicMock and monkeypatch `g.MemoryStore=_Mem`,
    `g.build_context_prefix=_bcp`; write a 1-probe probes.json; call `g.main([...,"--layers",
    "wikirag"])` with NO `--wiki-dir`. Assert rc != 0 (wikirag is the only arm); assert
    `subprocess.run.call_count == 0`; assert a message mentioning "wiki-dir" appears in
    `capsys.readouterr().out`.
  </action>
  <verify>
    <automated>.venv/bin/python -m pytest tests/test_bench_grounding.py -q</automated>
  </verify>
  <acceptance_criteria>
    - All new wikirag/retrieval/sanitizer tests pass; existing grounding tests unchanged and green.
    - `.venv/bin/python -m pytest tests/ --cov=flowstate --cov-fail-under=80` exits 0.
    - `.venv/bin/python -m ruff check flowstate/ bench/ tests/` and `.venv/bin/python -m ruff format --check` pass.
  </acceptance_criteria>
  <done>New tests cover ranking, k-cap, missing/empty dir, special-char query, wikirag arm record shape + bcp-skip, and no-wiki-dir guard; full suite + coverage + ruff all green.</done>
</task>

</tasks>

<verification>
- `.venv/bin/python -m pytest tests/ --cov=flowstate --cov-fail-under=80` exits 0.
- `.venv/bin/python -m ruff check flowstate/ bench/ tests/` clean.
- `.venv/bin/python -m ruff format --check` clean.
- Only `bench/grounding.py` and `tests/test_bench_grounding.py` modified (`git diff --name-only`).
</verification>

<success_criteria>
- `wikirag` is a selectable `--layers` arm with `--wiki-dir`/`--rag-k` args.
- Per-probe wikirag retrieval uses FTS5/BM25 mirroring memory.py; never raises.
- wikirag per-probe records expose `retrieved` article paths; build_context_prefix is skipped.
- Missing --wiki-dir is handled gracefully (clear message, no claude calls, non-zero when only arm).
- Aggregation/Wilson/delta/JSON/console output shape unchanged; existing arms intact.
- Full suite + coverage + ruff green.
</success_criteria>

<output>
Create `.planning/quick/260617-idb-add-wikirag-retrieval-arm-fts5-bm25-over/260617-idb-SUMMARY.md` and a bare `SUMMARY.md` in the same dir when done (status: complete).
</output>
