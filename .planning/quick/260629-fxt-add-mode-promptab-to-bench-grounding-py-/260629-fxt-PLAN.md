---
phase: quick-260629-fxt
plan: 01
type: tdd
wave: 1
depends_on: []
files_modified:
  - bench/grounding.py
  - tests/test_bench_grounding.py
  - bench/fixtures/instr_baseline.txt
  - bench/fixtures/instr_candidate.txt
autonomous: true
requirements: [QUICK-260629-fxt]
must_haves:
  truths:
    - "Running bench.grounding with --mode promptab A/B-tests two answer-instruction variants over one fixed context arm and prints a summary table with a decision"
    - "promptab emits JSON with mode/arm/variant_a/variant_b/delta/ci_overlap/decision keys when --out is given"
    - "decision is ADOPT_B only when B beats A AND their Wilson CIs do not overlap, else NO_CHANGE"
    - "promptab never raises: unreadable variant file or a retrieval arm (wikirag/wikivec) prints a note and returns 1"
    - "layers and rgb modes are byte-for-byte unchanged"
  artifacts:
    - path: "bench/grounding.py"
      provides: "_read_variant helper + _run_promptab dispatcher + --variant-a/--variant-b flags + promptab dispatch in main"
      contains: "_run_promptab"
    - path: "bench/fixtures/instr_baseline.txt"
      provides: "Variant A instruction reproducing today's default trailer"
    - path: "bench/fixtures/instr_candidate.txt"
      provides: "Variant B candidate instruction to test"
    - path: "tests/test_bench_grounding.py"
      provides: "Offline tests for _read_variant, ci_overlap/decision logic, JSON shape, retrieval-arm guard, never-raises"
  key_links:
    - from: "main()"
      to: "_run_promptab"
      via: "if args.mode == 'promptab': return _run_promptab(args, probes)"
      pattern: "args.mode == \"promptab\""
    - from: "_run_promptab"
      to: "build_context_prefix"
      via: "single fixed arm = args.layers[0] via _LAYERS_MAP"
      pattern: "build_context_prefix"
---

<objective>
Add an additive third bench mode `--mode promptab` to `bench/grounding.py` that A/B-tests two
answer-INSTRUCTION variants (the keyword-only `instruction=` trailer that `_answer` already
accepts), holding the context layer constant, and applies an eval-gated decision rule based on
Wilson-CI overlap.

Purpose: enables step 1 of a prompt-tuning A/B experiment — measure whether a candidate answer
instruction beats the current default with statistical separation, not vibes.

Output: new `_read_variant` + `_run_promptab` functions, two CLI flags, a `main()` dispatch
branch, two fixture instruction files, and offline tests. ADD-ONLY — no existing code path is
modified.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@/Users/jhogan/frameworx/CLAUDE.md

# The file being extended — study the _run_rgb envelope, the never-raises _rgb_* helpers,
# the layers-mode prefix build (lines 889-897), _wilson, _answer, _factcheck, _LAYERS_MAP usage.
@bench/grounding.py

# Test conventions to mirror — monkeypatch _answer/_factcheck to avoid real claude; main([...])
# invocation idiom; _bcp / _Mem stubs; RGB end-to-end tests at lines 1064+.
@tests/test_bench_grounding.py

# Fixture conventions.
@bench/fixtures/rgb_probes.example.json

<interfaces>
<!-- Key contracts the executor needs — already in bench/grounding.py; do NOT modify these. -->

_answer(prefix: str, question: str, model: str, *, instruction: str = "Answer concisely and specifically.") -> str
    # Never-raises. instruction= replaces the trailing prompt trailer.

_factcheck(answer: str, ground_truth: str, model: str) -> bool | None
    # Never-raises. True/False/None.

_wilson(successes: int, n: int) -> tuple[float, float]
    # Never-raises. (low, high) clamped to [0,1]; n==0 -> (0.0, 0.0).

build_context_prefix(root, mem, query=..., include_layers=...) -> str    # imported
_LAYERS_MAP: dict[str, ...]    # imported from bench.compound_eval; keys include none/pack/memory/wiki/full
MemoryStore(root=...)          # context manager

# Layers-mode non-retrieval prefix build (grounding.py ~889-897) — replicate this exactly:
#   with MemoryStore(root=root) as mem:
#       prefix = build_context_prefix(root, mem, query=probe["question"],
#                                     include_layers=_LAYERS_MAP[arm])

# Multi-judge majority idiom (grounding.py ~899-905):
#   if answer == "": votes = [None] * len(judge_models)
#   else: votes = [_factcheck(answer, probe["ground_truth"], m) for m in judge_models]
#   yes = sum(1 for v in votes if v is True); majority = yes > len(judge_models) / 2

# main() budget env-var save/restore envelope wraps the dispatch; promptab branch goes
# INSIDE the try, alongside the rgb branch (grounding.py ~846).
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1 (RED): Fixtures + failing promptab tests</name>
  <files>bench/fixtures/instr_baseline.txt, bench/fixtures/instr_candidate.txt, tests/test_bench_grounding.py</files>
  <behavior>
    Fixtures:
    - instr_baseline.txt: EXACTLY `Answer concisely and specifically.` (matches today's _answer default trailer so Variant A reproduces current behavior). Single line; _read_variant strips, so a trailing newline is harmless but avoid extra content.
    - instr_candidate.txt: EXACTLY `Answer concisely and specifically. Cite the exact fact from the context that supports your answer; if the context does not contain it, say so.`

    Tests (append a new section to tests/test_bench_grounding.py, mirroring the RGB end-to-end
    style: monkeypatch g._answer / g._factcheck so NO real claude binary is needed; stub
    g.build_context_prefix with _bcp and g.MemoryStore with _Mem; invoke via g.main([...]) or
    call g._run_promptab directly). Cover at minimum:
    - test__read_variant_happy_and_missing: write a tmp file with text → _read_variant returns
      stripped text; a non-existent path → returns None and does NOT raise.
    - test_promptab_adopt_b_when_b_wins_nonoverlapping: monkeypatch _answer to return a distinct
      string per variant (key off the instruction kwarg) and _factcheck so Variant A scores 0/N
      and Variant B scores N/N across enough probes×trials that the Wilson CIs do NOT overlap →
      assert decision == "ADOPT_B", ci_overlap is False, delta > 0.
    - test_promptab_no_change_when_tie_overlap: make both variants score identically (overlapping
      CIs) → assert decision == "NO_CHANGE" and ci_overlap is True.
    - test_promptab_json_shape: pass --out tmp file → assert the written JSON has keys mode
      (== "promptab"), arm, trials, answer_model, judge_models, variant_a, variant_b, delta,
      ci_overlap, decision; and that variant_a/variant_b each have accuracy, n, wilson_ci
      (a 2-list), text_sha (12-hex string).
    - test_promptab_retrieval_arm_returns_1: --layers wikivec (or wikirag) → _run_promptab returns
      1, prints a note, makes no crash; subprocess.run not required.
    - test_promptab_unreadable_variant_returns_1: point --variant-a at a missing path → returns 1,
      no raise.
    To force non-overlapping CIs cheaply, use several probes and/or --trials high enough; pick a
    fake _answer/_factcheck that gives A all-wrong and B all-right. _wilson(N,N) lower bound vs
    _wilson(0,N) upper bound separate for N>=5.
  </behavior>
  <action>
    Create the two fixture files under bench/fixtures/ with the EXACT instruction strings above.
    Append a new clearly-commented test section to tests/test_bench_grounding.py implementing the
    behaviors listed. Reuse the existing _bcp and _Mem stubs and the monkeypatch idiom already in
    the file (see the RGB end-to-end tests). Tests MUST run offline — monkeypatch g._answer and
    g._factcheck (and g.build_context_prefix / g.MemoryStore) so no claude binary or network is
    touched. These tests reference g._read_variant and g._run_promptab / promptab CLI flags that do
    not exist yet, so the suite is RED until Task 2.
  </action>
  <verify>
    <automated>cd /Users/jhogan/frameworx && python -m pytest tests/test_bench_grounding.py -q -k promptab 2>&1 | tail -5 ; ruff check tests/test_bench_grounding.py</automated>
  </verify>
  <done>Fixture files exist with exact strings; new promptab tests are added and FAIL (AttributeError on _run_promptab / _read_variant or unrecognized --mode choice), confirming the RED gate.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2 (GREEN): Implement _read_variant, _run_promptab, CLI flags, dispatch</name>
  <files>bench/grounding.py</files>
  <behavior>
    Make the Task 1 tests pass without modifying any existing code path (layers arm loop, RGB,
    _answer, _factcheck, _wilson, build_context_prefix, context_prefix stay byte-identical).

    _read_variant(path: Path) -> str | None — never-raises; returns path.read_text().strip() or
    None on any error.

    _run_promptab(args, probes) -> int — never-raises (wrap body in try/except returning 1),
    mirroring _run_rgb's structure:
    - Read a_text = _read_variant(args.variant_a), b_text = _read_variant(args.variant_b). If
      either is None → print a note and return 1.
    - arm = args.layers[0]. If arm in {"wikirag", "wikivec"} → print a note (promptab supports only
      build_context_prefix arms) and return 1.
    - judge_models = [m.strip() for m in args.judge_models.split(",") if m.strip()].
    - For each (label, text) in (("a", a_text), ("b", b_text)): accumulate successes/n over
      args.trials × probes. For each probe, build the prefix exactly like layers-mode non-retrieval
      arms: `with MemoryStore(root=args.root) as mem: prefix = build_context_prefix(args.root, mem,
      query=probe["question"], include_layers=_LAYERS_MAP[arm])`. Then
      `answer = _answer(prefix, probe["question"], args.answer_model, instruction=text)` and the
      multi-judge majority idiom (empty answer → all-None votes → not majority). Count majority as a
      success.
    - Per variant: accuracy = successes / n if n else 0.0; (lo, hi) = _wilson(successes, n);
      text_sha = hashlib.sha1(text.encode()).hexdigest()[:12].
    - delta = round(b_acc - a_acc, 3).
    - ci_overlap = not (b_low > a_high or a_low > b_high).
    - decision = "ADOPT_B" if (b_acc > a_acc and not ci_overlap) else "NO_CHANGE".
    - JSON (when args.out is not None, wrapped in try/except print warning):
      {"mode": "promptab", "arm": arm, "trials": args.trials, "answer_model": args.answer_model,
       "judge_models": judge_models, "variant_a": {"accuracy", "n", "wilson_ci": [lo, hi],
       "text_sha"}, "variant_b": {...}, "delta", "ci_overlap", "decision"}.
    - Always print a console summary table in the _run_rgb visual style: header + a row per variant
      (label, accuracy, wilson_ci, n), then a final line: delta / ci_overlap / decision.
    - Return 1 when both variants produced n == 0, else 0.

    CLI (additive in _build_parser): add `parser.add_argument("--variant-a", type=Path)` and
    `--variant-b` (Path); change the existing `--mode` choices from ("layers", "rgb") to
    ("layers", "rgb", "promptab"). Reuse existing --layers/--probes/--root/--trials/--answer-model/
    --judge-models/--out. Add NO redundant flags. Note: --layers default is
    ["none","pack","wiki"]; promptab uses args.layers[0] (= "none" by default), so a user passes a
    single arm via --layers.

    Dispatch in main(): immediately after the existing `if args.mode == "rgb": return
    _run_rgb(args, probes)` add `if args.mode == "promptab": return _run_promptab(args, probes)`,
    inside the existing budget env-var save/restore try-block, before the layers arm loop.

    Add `import hashlib` to the stdlib import block (alphabetical placement near the other imports).
  </behavior>
  <action>
    Edit bench/grounding.py: add `import hashlib` to the stdlib imports; add _read_variant and
    _run_promptab functions (place the dispatcher in a new commented section after the RGB
    dispatcher, mirroring _run_rgb's never-raises envelope); add the two CLI flags and extend the
    --mode choices tuple in _build_parser; add the promptab dispatch line in main() next to the rgb
    branch. Touch ONLY new code — do not alter existing functions or their bodies. Keep ruff format
    (line-length 100, double quotes, snake_case). Do not place fenced code blocks inside docstrings
    that would change existing behavior.
  </action>
  <verify>
    <automated>cd /Users/jhogan/frameworx && python -m pytest tests/test_bench_grounding.py -q 2>&1 | tail -8 && ruff check bench/grounding.py tests/test_bench_grounding.py && ruff format --check bench/grounding.py tests/test_bench_grounding.py && python -m pytest tests/ --cov=flowstate --cov-fail-under=80 -q 2>&1 | tail -5</automated>
  </verify>
  <done>All promptab tests pass; full tests/test_bench_grounding.py green; layers and rgb tests still pass unchanged; ruff check + format --check clean; the --cov-fail-under=80 gate still holds.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| filesystem → bench | variant instruction files and probes JSON read from local disk (research operator-controlled) |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-fxt-01 | Tampering/DoS | _read_variant / _run_promptab file + subprocess paths | mitigate | never-raises envelopes (try/except → None / return 1); no new deps; stdlib-only (hashlib for SHA) |
| T-fxt-02 | Information disclosure | instruction text in JSON output | accept | research tooling, operator-local files, no secrets; text_sha is a non-reversible provenance tag |
| T-fxt-SC | Tampering | npm/pip/cargo installs | accept | none — no package installs in this task (stdlib + existing deps only) |
</threat_model>

<verification>
- `python -m pytest tests/test_bench_grounding.py -q` passes.
- `python -m pytest tests/ --cov=flowstate --cov-fail-under=80 -q` holds the 80% gate.
- `ruff check bench/grounding.py tests/test_bench_grounding.py` and
  `ruff format --check bench/grounding.py tests/test_bench_grounding.py` are clean.
- `git diff` shows the layers-mode arm loop, RGB code, _answer, _factcheck, _wilson,
  build_context_prefix, and context_prefix are unchanged (additions only).
</verification>

<success_criteria>
- `--mode promptab` runs an A/B over two instruction variants on a single fixed context arm and
  prints accuracy + Wilson CI per variant plus delta / ci_overlap / decision.
- decision == "ADOPT_B" iff B beats A with non-overlapping CIs, else "NO_CHANGE".
- JSON output (when --out) matches the documented shape including per-variant text_sha.
- Retrieval arm (wikirag/wikivec) or unreadable variant → return 1 with a note, no crash.
- Two fixture files exist with the exact baseline/candidate strings.
- layers and rgb modes are byte-for-byte unchanged; coverage gate and ruff stay green.
</success_criteria>

<output>
Create `.planning/quick/260629-fxt-add-mode-promptab-to-bench-grounding-py-/SUMMARY.md`
and `.planning/quick/260629-fxt-add-mode-promptab-to-bench-grounding-py-/260629-fxt-SUMMARY.md`
when done (status: complete).
</output>
