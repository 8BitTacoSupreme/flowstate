---
phase: quick-260709-rep
plan: 01
type: tdd
wave: 1
depends_on: []
files_modified:
  - bench/locomo.py
  - tests/test_locomo.py
autonomous: true
requirements: [REP-01]
must_haves:
  truths:
    - "`--corpus turns` (default) reproduces prior numbers byte-identically"
    - "`--corpus observations` retrieves over observation docs whose ids are dia_ids"
    - "`_build_observation_docs` emits (dia_id, text) docs, handles list-of-dia_ids, never raises"
    - "output JSON records the corpus value"
  artifacts:
    - path: bench/locomo.py
      provides: "_build_observation_docs + --corpus flag + corpus in output JSON"
      contains: "_build_observation_docs"
    - path: tests/test_locomo.py
      provides: "observation-doc + --corpus coverage tests"
      contains: "_build_observation_docs"
  key_links:
    - from: bench/locomo.py
      to: bench/_retrieval.py
      via: "module-attribute ranker access (_retrieval.bm25_rank)"
      pattern: "_retrieval\\.(bm25_rank|semantic_rank)"
---

<objective>
Add an `--corpus turns|observations` arm to `bench/locomo.py`. The LoCoMo paper's best RAG
arm retrieved over **observations** (assertive summaries carrying `dia_id` provenance), not
raw turns. Because observation doc ids ARE dia_ids, evidence-coverage scoring is unchanged and
metric-compatible with the turns corpus.

Purpose: Enable an apples-to-apples turns-vs-observations retrieval comparison on LoCoMo.
Output: `_build_observation_docs`, `--corpus` flag (default `turns`, byte-identical), `corpus`
recorded in output JSON, plus extended offline tests.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@/Users/jhogan/frameworx/CLAUDE.md

Scope lock: modify ONLY `bench/locomo.py` + `tests/test_locomo.py`. Do NOT touch
`bench/locomo_qa.py`, `bench/longmemeval*.py`, `bench/_retrieval.py`, `bench/grounding.py`,
`flowstate/`, `pyproject.toml`, or `bench/fixtures/locomo_smoke.json`. Prove scope with
`git diff --name-only`.

<interfaces>
Existing bench/locomo.py contracts (unchanged, build against these):
- `_build_docs(conv) -> list[tuple[str,str]]` — turns builder; never-raises → []
- `_coverage(gold, retrieved) -> float`, `_full_coverage(gold, retrieved) -> int`
- `main(argv) -> int`; rankers accessed via `import bench._retrieval as _retrieval`
- output dict keys: benchmark, n_qa, skipped, top_n, embed_model, backends

Real-data structure (locomo10.json), verified:
- conv["conversation"]["session_N"] = list of {speaker, dia_id, text}  (turns corpus)
- conv["observation"]["session_N_observation"] = { "<Speaker>": [ [obs_text, dia_id], ... ] }
  * 2nd element is USUALLY a dia_id string ("D10:3") but MAY be a list of dia_ids — handle BOTH.
- conv["session_summary"]["session_N_summary"] = plain string, NO provenance → NOT usable for
  evidence-coverage. Do NOT add a summaries corpus; document why in the module docstring.
</interfaces>
</context>

<tasks>

<task type="tdd" tdd="true">
  <name>Task 1 (RED): failing tests for _build_observation_docs and --corpus observations</name>
  <files>tests/test_locomo.py</files>
  <behavior>
    - `_build_observation_docs`: dict-of-speaker → list of [text, dia] → correct (dia_id, text) docs.
    - 2nd element as a LIST of dia_ids → one doc per id (same text).
    - Malformed rows (non-list, wrong-length, non-dict session value) skipped; never raises.
    - Missing "observation" key → [] (never raises).
    - `--corpus observations` end-to-end: tiny inline conv written to a tmp JSON, bm25 backend,
      gold-evidence dia_id (that appears in an observation) is retrieved within top-n; coverage
      math correct (mean_coverage / full_coverage_rate reflect the hit).
    - output JSON contains key "corpus" == "observations".
    - `--corpus turns` default path: existing tests stay green; the turns builder is used
      (assert corpus defaults to "turns" in JSON when flag omitted).
  </behavior>
  <action>
    Extend tests/test_locomo.py (do NOT modify the smoke fixture). Add tests referencing
    `loc._build_observation_docs` and a `--corpus` flag that do not yet exist, so the suite fails
    RED. Use inline dict fixtures written to `tmp_path` JSON for the observations end-to-end test
    (a minimal conv with "conversation", "observation", and a "qa" whose evidence dia_id appears
    in an observation). Cover: string-dia and list-of-dia rows, malformed-row skipping, missing
    key → [], JSON "corpus" presence, and default-corpus == "turns". Run `ruff check --fix` on the
    test file to satisfy I001 for the `import bench._retrieval as _retrieval` idiom if used.
    Commit: `test(260709-rep): failing tests for observations corpus arm`.
  </action>
  <verify>
    <automated>cd /Users/jhogan/frameworx && python -m pytest tests/test_locomo.py -q 2>&1 | grep -Eq 'error|failed|AttributeError'</automated>
  </verify>
  <done>New tests fail because `_build_observation_docs` and `--corpus` do not yet exist; test file is ruff-clean.</done>
</task>

<task type="tdd" tdd="true">
  <name>Task 2 (GREEN): implement _build_observation_docs + --corpus flag</name>
  <files>bench/locomo.py</files>
  <behavior>
    - `_build_observation_docs(conv) -> list[tuple[str,str]]` never-raises → [].
    - `--corpus` choices ("turns","observations"), default "turns"; turns path byte-identical.
    - output JSON gains "corpus"; console summary notes the corpus.
  </behavior>
  <action>
    Add `_build_observation_docs(conv)`: wrap in try/except → []. Get `conv.get("observation", {})`;
    for each session key, for each speaker → row-list, for each row: require a list/tuple of
    length 2 → (text, dia). If dia is a list, emit one `(str(d), str(text))` per element; if dia is
    a str, emit `(str(dia), str(text))`. Skip anything malformed (wrong type/shape). Dedup NOT
    required — document the choice in the docstring. Note in the docstring WHY session_summary is
    excluded (no dia_id provenance → incompatible with evidence-coverage).

    Add `--corpus` argparse arg (choices=("turns","observations"), default="turns"). In the conv
    loop select the builder: `turns` → existing `_build_docs`; `observations` →
    `_build_observation_docs`. Keep `_build_docs` and all scoring UNCHANGED so the turns path is
    byte-identical (prior numbers reproduce). Add `"corpus": args.corpus` to the `output` dict and
    mention the corpus in the console summary. Keep module-attribute ranker access
    (`_retrieval.bm25_rank`). ruff: 100-col, double quotes. Commit:
    `feat(260709-rep): add --corpus turns|observations arm to locomo`.
  </action>
  <verify>
    <automated>cd /Users/jhogan/frameworx && python -m pytest tests/test_locomo.py -q && ruff check bench/locomo.py tests/test_locomo.py && ruff format --check bench/locomo.py tests/test_locomo.py</automated>
  </verify>
  <done>All locomo tests green; ruff check + format --check clean on both files.</done>
</task>

</tasks>

<verification>
- `cd /Users/jhogan/frameworx && python -m pytest tests/ --cov=flowstate --cov-fail-under=80 -q` passes.
- `ruff check bench/locomo.py tests/test_locomo.py` and `ruff format --check` both clean.
- `git diff --name-only` lists ONLY `bench/locomo.py` and `tests/test_locomo.py`.
- Turns path byte-identical: pre-existing locomo tests remain green unchanged.
</verification>

<success_criteria>
- `_build_observation_docs` emits dia_id-keyed docs (string-dia and list-of-dia), skips malformed
  rows, returns [] on missing key — never raises.
- `--corpus turns` (default) reproduces prior behavior; `--corpus observations` retrieves over
  observation docs and scores via unchanged evidence-coverage.
- Output JSON records `"corpus"`.
- Scope limited to the 2 files.
</success_criteria>

<output>
Create `.planning/quick/260709-rep-add-corpus-turns-observations-arm-to-ben/SUMMARY.md`
and `.planning/quick/260709-rep-add-corpus-turns-observations-arm-to-ben/260709-rep-SUMMARY.md`
when done (status: complete).
</output>
