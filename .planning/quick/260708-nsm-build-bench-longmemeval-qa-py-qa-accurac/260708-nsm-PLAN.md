---
phase: 260708-nsm
plan: 01
type: tdd
wave: 1
depends_on: []
files_modified:
  - bench/longmemeval_qa.py
  - tests/test_longmemeval_qa.py
autonomous: true
requirements: [NSM-QA-B]
must_haves:
  truths:
    - "python -m pytest tests/test_longmemeval_qa.py -q passes fully offline (no real claude, no embedder)"
    - "The retrieval arm produces per-question-type AND overall QA accuracy with Wilson CIs"
    - "The oracle arm reads from gold answer_session_ids and reports the reader ceiling"
    - "A None judge counts as incorrect but is tallied in n"
    - "--limit caps the number of instances processed"
    - "bench/longmemeval.py, bench/_retrieval.py, bench/grounding.py, and flowstate/ are byte-for-byte UNCHANGED"
  artifacts:
    - path: "bench/longmemeval_qa.py"
      provides: "LongMemEval QA-accuracy Task B harness (retrieve -> read -> judge -> per-type accuracy)"
      contains: "def _run_qa"
    - path: "tests/test_longmemeval_qa.py"
      provides: "Offline test suite mirroring the Task A / grounding monkeypatch idiom"
      contains: "def test_"
  key_links:
    - from: "bench/longmemeval_qa.py"
      to: "bench.longmemeval._build_docs / _load_data"
      via: "module-attribute import (import bench.longmemeval as _lme; _lme._build_docs(...))"
      pattern: "import bench.longmemeval as"
    - from: "bench/longmemeval_qa.py"
      to: "bench._retrieval.bm25_rank / semantic_rank / semantic_backend_available"
      via: "module-attribute import (import bench._retrieval as _r; _r.bm25_rank(...))"
      pattern: "import bench._retrieval as"
    - from: "bench/longmemeval_qa.py"
      to: "bench.grounding._answer / _factcheck / _judge_rejection / _wilson"
      via: "module-attribute import (import bench.grounding as _g; _g._answer(...))"
      pattern: "import bench.grounding as"
---

<objective>
Build `bench/longmemeval_qa.py` — the LongMemEval QA-accuracy layer ("Task B"): retrieve
top-k sessions -> feed them to a claude reader -> judge the answer against gold -> report
per-question-type + overall accuracy with Wilson CIs. This is the headline number
comparable to the LongMemEval leaderboard / paper Table 2.

Purpose: FlowState already measures session-level Recall@k (Task A, bench/longmemeval.py).
Task B closes the loop end-to-end so retrieval-backend quality can be scored as QA accuracy,
not just recall.

Output: New files `bench/longmemeval_qa.py` + `tests/test_longmemeval_qa.py`. ADD-ONLY —
imports from Task A / _retrieval / grounding; modifies none of them.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@/Users/jhogan/frameworx/CLAUDE.md
@bench/longmemeval.py
@bench/_retrieval.py
@bench/grounding.py
@tests/test_longmemeval.py
@bench/fixtures/lme_smoke.json

<interfaces>
<!-- Verified signatures — call ALL of these via module attribute so tests can monkeypatch. -->

From bench/longmemeval.py:
  def _load_data(path: Path | str) -> list[dict] | None
  def _build_docs(instance: dict) -> list[tuple[str, str]] | None   # (session_id, session_text)

From bench/_retrieval.py:
  def bm25_rank(docs: list[tuple[str, str]], query: str, k: int) -> list[str]        # ranked session ids
  def semantic_rank(docs: list[tuple[str, str]], query: str, k: int, embed_fn) -> list[str]  # embed_fn is 4th POSITIONAL
  def semantic_backend_available(embed_model: str) -> tuple  # -> (embed_fn | None, bool)

From bench/grounding.py:
  def _answer(prefix: str, question: str, model: str, *, instruction: str = "...") -> str  # "" on failure/no binary
  def _factcheck(answer: str, ground_truth: str, model: str) -> bool | None                 # True/False/None
  def _judge_rejection(answer: str, model: str) -> bool | None                              # EXISTS (line 358); regex fast-path then LLM
  def _wilson(successes: int, n: int) -> tuple[float, float]                                # (low, high), n==0 -> (0.0, 0.0)

Instance schema (confirmed against bench/fixtures/lme_smoke.json, 3 instances):
  keys: question_id, question_type, question, answer (gold string), question_date,
        haystack_session_ids, haystack_dates, haystack_sessions, answer_session_ids
  turns are {role, content}; NO has_answer in cleaned data — do NOT depend on it.
  Fixture instances: lme-001 single_session gold=['sess-001'];
                     lme-002 multi_session gold=['sess-005','sess-006'];
                     lme-003 abstention gold=[] (question_type == "abstention", does NOT end "_abs").

Task A call pattern for semantic (mirror exactly): resolve via
  embed_fn, available = _r.semantic_backend_available(embed_model)
then rank via  _r.semantic_rank(docs, q, k, embed_fn).
</interfaces>
</context>

<tasks>

<task type="tdd" tdd="true">
  <name>Task 1 (RED): Write the offline test suite for longmemeval_qa</name>
  <files>tests/test_longmemeval_qa.py</files>
  <behavior>
    Mirror the idiom of tests/test_longmemeval.py and tests/test_bench_grounding.py:
    fully offline, monkeypatch every LLM/embedder/ranker seam via MODULE ATTRIBUTE so no
    real `claude` binary or fastembed is ever invoked. `import bench.longmemeval_qa as qa`.

    Write these tests (RED — module does not exist yet, so all fail on ImportError/AttributeError):

    - test_reader_context_separates_and_orders: given docs [(id,text)...] and session_ids in a
      chosen order, `qa._reader_context(docs, ids)` concatenates the selected texts joined by
      "\n\n---\n\n" in the requested id order. Ids not present in docs are ignored.
    - test_reader_context_respects_char_budget: with char_budget small, output length <= char_budget.
    - test_reader_context_empty_ids_returns_empty: empty ids -> "".
    - test_reader_context_never_raises: pass a malformed docs list / None -> returns "" (no raise).

    - test_judge_one_passthrough: monkeypatch bench.grounding._factcheck (via module attr) to
      return True, then False, then None; assert `qa._judge_one(answer, instance, "sonnet")`
      returns each verbatim. Never raises.

    - test_run_qa_retrieval_per_type_and_overall: build an args namespace
      (use argparse.Namespace or qa._build_parser().parse_args([...])) with backend=bm25,
      arms="retrieval", k=5, limit=None, reader_model/judge_model="sonnet", char_budget=48000,
      out=<tmp>. Construct 3 instances across 2 question_types (e.g. two "single_session" and
      one "multi_session"). Monkeypatch bench.longmemeval._build_docs to return a fixed docs
      list, bench._retrieval.bm25_rank to return known ids, bench.grounding._answer to return a
      fixed non-empty string, and bench.grounding._factcheck so a KNOWN subset is correct
      (e.g. single_session 2/2 correct, multi_session 0/1 correct). Assert:
        * arms["retrieval"]["by_type"]["single_session"]["accuracy"] == 1.0, n == 2
        * arms["retrieval"]["by_type"]["multi_session"]["accuracy"] == 0.0, n == 1
        * arms["retrieval"]["overall"]["accuracy"] == pytest.approx(2/3), n == 3
        * each block has a "wilson_ci" (2-element list/tuple)
      Read the aggregation from the written JSON at args.out.

    - test_run_qa_oracle_uses_answer_session_ids: arms="oracle". Monkeypatch _answer/_factcheck;
      spy that the context handed to _answer is built from instance["answer_session_ids"]
      (e.g. monkeypatch qa._reader_context or _answer to capture the ids/context). Assert oracle
      block aggregation is correct.

    - test_run_qa_limit_caps_instances: 4 instances, limit=2 -> only 2 scored (assert overall n == 2
      and output records limit == 2).

    - test_run_qa_none_judge_counts_incorrect_but_in_n: _factcheck monkeypatched to return None
      for one instance and True for another -> accuracy == 0.5 over n == 2 (None is incorrect,
      still tallied).

    - test_run_qa_returns_one_when_zero_scored: empty instance list (or all malformed) -> _run_qa
      returns 1.

    - test_run_qa_malformed_instance_skipped_no_crash: one instance where _build_docs returns None
      (monkeypatch to None for it) -> skipped, no exception, rc is int.

    - test_main_e2e_bm25_offline: use bench/fixtures/lme_smoke.json OR a tiny inline 3-session
      fixture written to tmp_path. Run qa.main(["--data", <path>, "--backend", "bm25",
      "--arms", "retrieval,oracle", "--k", "5", "--limit", "2", "--out", <tmp>])
      with bench.grounding._answer and bench.grounding._factcheck monkeypatched (real bm25 over
      the sessions is fine — it's stdlib FTS5). Assert rc == 0 and the JSON has keys:
      benchmark=="longmemeval_qa", n_instances, limit, backend, k, reader_model, judge_model,
      and arms with "retrieval" and "oracle" each having "overall" and "by_type".

    Use a semantic-skip guard test only if trivial: monkeypatch
    bench._retrieval.semantic_backend_available -> (None, False), backend="semantic",
    assert main() still returns int and does not raise (semantic arm degrades like Task A).
  </behavior>
  <action>
    Create tests/test_longmemeval_qa.py. `from __future__ import annotations`. Import the target
    as `import bench.longmemeval_qa as qa` and monkeypatch collaborators on their OWNING module
    (bench.grounding._answer, bench.grounding._factcheck, bench.longmemeval._build_docs,
    bench._retrieval.bm25_rank, bench._retrieval.semantic_backend_available) — this matches the
    seam Task A adopted and only works if the impl calls them via module attribute.

    Build args either through qa._build_parser().parse_args([...]) (preferred, exercises the CLI)
    or argparse.Namespace with every attribute the impl reads. Read aggregation results from the
    JSON written to args.out (mirrors test_longmemeval.py which asserts on the out file), not from
    a return value. Keep fixtures tiny and inline where a fixture file is not already suitable;
    reuse bench/fixtures/lme_smoke.json for the e2e where convenient.

    Do NOT invoke a real claude binary or fastembed anywhere. ruff format (line-length 100,
    double quotes), snake_case.
  </action>
  <verify>
    <automated>cd /Users/jhogan/frameworx && python3 -m pytest tests/test_longmemeval_qa.py -q 2>&1 | grep -Eiq "error|no module named 'bench.longmemeval_qa'|attributeerror|failed" && echo "RED-OK: tests fail (module absent)" || echo "UNEXPECTED: tests already pass"</automated>
  </verify>
  <done>tests/test_longmemeval_qa.py exists, is ruff-clean, and fails only because bench/longmemeval_qa.py does not yet exist (RED state confirmed).</done>
</task>

<task type="tdd" tdd="true">
  <name>Task 2 (GREEN): Implement bench/longmemeval_qa.py to pass the suite</name>
  <files>bench/longmemeval_qa.py</files>
  <behavior>
    All Task 1 tests go GREEN. Never-raises throughout; stdlib + flowstate + bench.* imports only;
    no new third-party deps. fastembed/sqlite_vec optional (semantic arm degrades/skips like Task A).
  </behavior>
  <action>
    Create bench/longmemeval_qa.py. `from __future__ import annotations`. Module docstring MUST
    state this is a TRANSPARENT REPRODUCTION using a single binary faithful judge
    (bench.grounding._factcheck), NOT the paper's official per-question-type GPT-4o judge prompts;
    note judge_model is configurable so a different judge can be swapped later. Mark ADD-ONLY.

    Imports (module attribute seam — REQUIRED so tests can monkeypatch):
      import argparse, json, sys; from pathlib import Path
      import bench.longmemeval as _lme
      import bench._retrieval as _r
      import bench.grounding as _g

    Implement exactly:

    1) _reader_context(docs, session_ids, *, char_budget=48000) -> str — build {id: text} from docs,
       then join texts for session_ids IN ORDER (skip ids absent from docs) with "\n\n---\n\n",
       truncate result to char_budget. Wrap in try/except -> "" on any error.

    2) _answer_one(instance, ids, reader_model, char_budget) -> str — docs = _lme._build_docs(instance);
       if None -> ""; context = _reader_context(docs, ids, char_budget=char_budget);
       return _g._answer(context, instance["question"], reader_model). try/except -> "".

    3) _judge_one(answer, instance, judge_model) -> bool | None — if instance["question_type"]
       endswith "_abs": abstention path — correct iff the answer declines; use
       _g._judge_rejection(answer, judge_model) (it exists). Else return
       _g._factcheck(answer, instance["answer"], judge_model). try/except -> None.

    4) _run_qa(args, instances) -> int — wrap whole body in try/except -> return 1. Steps:
       - arms = comma-split args.arms (default "retrieval"); supported {"retrieval","oracle"}.
       - Apply args.limit (None = all) to cap instances; record the effective limit.
       - For "retrieval": for each instance, docs = _lme._build_docs(instance); skip (continue) if None.
         Rank ids: backend=="bm25" -> _r.bm25_rank(docs, q, args.k);
         backend=="semantic" -> resolve embed_fn, available = _r.semantic_backend_available(args.embed_model);
         if not available, print a skip note and skip the semantic arm (Task A parity);
         else ids = _r.semantic_rank(docs, q, args.k, embed_fn). Take ids[:k]. answer = _answer_one; judge.
       - For "oracle": ids = instance.get("answer_session_ids", []); answer = _answer_one; judge.
       - Aggregate PER question_type AND overall: for each bucket accuracy = correct/n,
         n = number scored, wilson_ci = list(_g._wilson(correct, n)). A None judge is INCORRECT
         (correct only when judge is True) but IS counted in n. Document this in a comment.
       - Build output dict: {"benchmark":"longmemeval_qa", "n_instances", "limit", "backend",
         "k", "reader_model", "judge_model", "arms": {arm: {"overall": {...}, "by_type": {qtype: {...}}}}}.
         Each stats block = {"accuracy", "n", "wilson_ci"}.
       - Write args.out (try/except around write, print warning on failure) — mirror Task A.
       - Print a grounding-style console table: per arm, overall accuracy + CI + n, then per-type rows.
       - Return 1 if zero instances scored across all arms, else 0.

    5) _build_parser() -> argparse.ArgumentParser + main(argv=None) -> int:
       flags: --data (Path, required), --backend {bm25,semantic} default semantic,
       --k int default 5, --arms default "retrieval", --reader-model default "sonnet",
       --judge-model default "sonnet", --embed-model default "BAAI/bge-small-en-v1.5",
       --char-budget int default 48000, --limit int default None, --out (Path, default None).
       main: instances = _lme._load_data(args.data); if None -> print note, return 1;
       else return _run_qa(args, instances).
       `if __name__ == "__main__": sys.exit(main())`.

    Do NOT modify bench/longmemeval.py, bench/_retrieval.py, bench/grounding.py, or flowstate/.
    ruff format (line-length 100, double quotes), snake_case.
  </action>
  <verify>
    <automated>cd /Users/jhogan/frameworx && python3 -m pytest tests/test_longmemeval_qa.py -q && ruff check bench/longmemeval_qa.py tests/test_longmemeval_qa.py && ruff format --check bench/longmemeval_qa.py tests/test_longmemeval_qa.py && git diff --quiet -- bench/longmemeval.py bench/_retrieval.py bench/grounding.py flowstate/ && echo "ADD-ONLY-CONFIRMED" && python3 -m pytest tests/ --cov=flowstate --cov-fail-under=80 -q</automated>
  </verify>
  <done>All test_longmemeval_qa.py tests pass; ruff clean; `git diff --quiet` confirms Task A / _retrieval / grounding / flowstate unchanged; the 80% coverage gate holds.</done>
</task>

</tasks>

<verification>
- `python3 -m pytest tests/test_longmemeval_qa.py -q` passes fully offline (no real claude, no embedder).
- `python3 -m pytest tests/ --cov=flowstate --cov-fail-under=80 -q` holds the 80% gate.
- `ruff check` + `ruff format --check` clean on both new files.
- `git diff --quiet -- bench/longmemeval.py bench/_retrieval.py bench/grounding.py flowstate/` — ADD-ONLY proof.
- Optional smoke (requires real `claude` binary, NOT a correctness gate — document in SUMMARY):
  `python3 -m bench.longmemeval_qa --data bench/fixtures/lme_smoke.json --backend bm25 --arms retrieval,oracle --k 5 --limit 2 --out /tmp/qa.json`
</verification>

<success_criteria>
- New module bench/longmemeval_qa.py implements _reader_context, _answer_one, _judge_one,
  _run_qa, _build_parser, main exactly as specified — never-raises, no scope expansion.
- Retrieval + oracle arms both report per-question-type AND overall accuracy with Wilson CIs.
- None-judge counts incorrect but tallied in n; --limit caps instances; semantic arm degrades
  gracefully when fastembed/sqlite_vec absent.
- All collaborators called via module attribute (monkeypatch seam); zero edits to Task A,
  _retrieval, grounding, or flowstate.
</success_criteria>

<output>
Create `.planning/quick/260708-nsm-build-bench-longmemeval-qa-py-qa-accurac/SUMMARY.md`
and `.planning/quick/260708-nsm-build-bench-longmemeval-qa-py-qa-accurac/260708-nsm-SUMMARY.md`
(both, per the SUMMARY convention) with `status:` frontmatter when done.
</output>
