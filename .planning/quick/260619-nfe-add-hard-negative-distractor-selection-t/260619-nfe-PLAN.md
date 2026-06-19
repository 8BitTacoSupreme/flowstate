---
phase: quick-260619-nfe
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - bench/grounding.py
  - tests/test_bench_grounding.py
autonomous: true
requirements: [RGBHN-01]
must_haves:
  truths:
    - "With no --hard-negatives flag, RGB distractor selection is byte-identical to today's id-order behavior"
    - "With --hard-negatives + a working embedder, distractors are reordered topically-nearest-first by cosine similarity to the probe question"
    - "Any failure in the embed/rank path falls back to id-order; the harness never raises"
    - "RGB JSON output records hard_negatives: true only when the flag is set AND an embedder was built"
  artifacts:
    - path: "bench/grounding.py"
      provides: "embed_fn-aware _rgb_distractors, new _rank_by_similarity helper, --hard-negatives CLI flag, hard_negatives output key"
      contains: "_rank_by_similarity"
    - path: "tests/test_bench_grounding.py"
      provides: "offline tests for hard-negative selection, byte-identity, never-raise, determinism/tie-break, and _run_rgb end-to-end with monkeypatched embedder"
      contains: "hard_negatives"
  key_links:
    - from: "bench/grounding.py:_rgb_distractors"
      to: "bench/grounding.py:_rank_by_similarity"
      via: "calls _rank_by_similarity when embed_fn is not None, inside try/except"
      pattern: "_rank_by_similarity"
    - from: "bench/grounding.py:_run_rgb"
      to: "bench/grounding.py:_default_embedder"
      via: "builds embed_fn in try/except when args.hard_negatives is set, threads into axis helpers"
      pattern: "_default_embedder"
---

<objective>
Add opt-in hard-negative distractor selection to the RGB axes in `bench/grounding.py`. When enabled, distractors are chosen from the same candidate pool but reordered topically-nearest-first (by cosine similarity to the probe question) using the existing embedder, instead of deterministic id-order.

Purpose: Stronger adversarial RGB evaluation — near-miss distractors are harder negatives than arbitrary id-ordered ones, producing a more discriminating noise/negative/integration signal.

Output: An `embed_fn`-aware `_rgb_distractors`, a pure-Python `_rank_by_similarity` helper, a `--hard-negatives` CLI flag (RGB-mode only, reusing `--embed-model`), a `hard_negatives` boolean in the RGB JSON, and a fully offline test suite. ADD-ONLY and bench-only; stdlib + OPTIONAL lazy fastembed; never-raises; default behavior preserved byte-for-byte.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@/Users/jhogan/frameworx/CLAUDE.md
@/Users/jhogan/frameworx/.claude/CLAUDE.md

<read_first>
Source under change — read these spans of `bench/grounding.py` before editing:
- Module docstring + ADD-ONLY / stdlib-only / never-raises / fastembed-optional rules (lines 1-55)
- `_default_embedder` (lines 155-173) — the existing lazy fastembed factory to reuse; raises RuntimeError when fastembed is absent
- `_rgb_distractors` (lines 404-426) — the function to extend; current behavior = probes sorted by id, exclude self, string gold → one passage, list gold → each item, cap at n, return [] on any exception
- `_rgb_noise` (lines 429-467), `_rgb_negative` (lines 470-497), `_rgb_integration` (lines 500-533) — the three callers that must thread `embed_fn` through to `_rgb_distractors`
- `_rgb_counterfactual` (lines 536-564) — uses NO distractors; leave it untouched
- `_run_rgb` (lines 572-716) — the RGB dispatcher; build `embed_fn` here and add `hard_negatives` to `output`
- `_build_parser` (lines 724-747) — where the RGB flags live; add `--hard-negatives`

Test patterns to mirror in `tests/test_bench_grounding.py`:
- `_fake_embed_factory` (lines 600-609) — deterministic offline fake `embed_fn(texts) -> list[list[float]]`; reuse/extend this pattern (no fastembed, no sqlite_vec, no network)
- `_RGB_PROBES_FIXTURE` (lines 814-844) — existing offline RGB probe fixture; reuse for distractor tests
- `test_rgb_distractors_excludes_self_deterministic_and_count` (lines 847-870) — existing id-order assertions to preserve
- `test_run_rgb_end_to_end_emits_per_axis_json` (lines 1064-1160) — the `--mode rgb` end-to-end harness pattern (monkeypatch `_answer`/`_factcheck`/`_judge_rejection`, write probes, read out.json)
- `test_wikivec_arm_records_retrieved_and_skips_bcp` (lines 668-712) — pattern for `monkeypatch.setattr(g, "_default_embedder", lambda model: ...)`
</read_first>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Add _rank_by_similarity and embed_fn-aware _rgb_distractors with byte-identical default + never-raise fallback</name>
  <files>bench/grounding.py, tests/test_bench_grounding.py</files>
  <behavior>
    Tests (add to tests/test_bench_grounding.py; all OFFLINE — inject a deterministic fake embed_fn; NO fastembed/sqlite_vec/network):
    - hard-neg selection: with a fake embed_fn that maps the probe question and ONE specific non-first candidate to the same vector and all others to a far vector, `_rgb_distractors(probe, probes, n, embed_fn=fake)` returns that near candidate FIRST, and the returned list differs from the `embed_fn=None` (id-order) result.
    - byte-identity: `_rgb_distractors(probe, probes, n, embed_fn=None)` returns EXACTLY the existing id-order list — assert against an explicit expected list literal built from _RGB_PROBES_FIXTURE gold order (do not just compare to another call).
    - never-raise: an embed_fn that raises RuntimeError → `_rgb_distractors` returns the id-order list (== the embed_fn=None result), no exception propagates.
    - determinism + stable tie-break: with a fake embed_fn that returns the SAME vector for every text (all ties), two successive calls return identical lists AND that list equals id-order (stable tie-break falls back to id order).
    - _rank_by_similarity direct: zero-norm guard — a candidate whose embedding is all-zeros does not raise (no ZeroDivision) and the function still returns a list of the same candidates.
  </behavior>
  <action>
    Add a new helper `_rank_by_similarity(query, candidates, embed_fn)` near the RGB axes helpers section (after `_rgb_counterfactual` or alongside `_rgb_distractors`). It makes ONE `embed_fn([query] + candidate_texts)` call (query first), splits off the query vector, then for each candidate computes cosine = dot(a,b)/(norm(a)*norm(b)) in PURE PYTHON using `math` only (norm = math.sqrt(sum(x*x))). Guard zero-norm: if either norm is 0.0, treat that candidate's similarity as -inf (or 0.0) so it sinks to the bottom without dividing by zero. Return `candidates` reordered DESCENDING by cosine, with a STABLE tie-break that preserves the input order (use `sorted(range(len(candidates)), key=lambda i: (-sim[i],), )` style on enumerated indices, or `sorted(enumerate(candidates), key=lambda t: -sim[t[0]])` — Python sort is stable, so equal sims keep input order). Do NOT use sqlite_vec here — this is a tiny in-memory list, plain Python. `_rank_by_similarity` itself does not need its own try/except (the caller wraps it), but it must not raise on zero-norm.

    Extend `_rgb_distractors(probe, probes, n)` signature to `_rgb_distractors(probe, probes, n, embed_fn=None)`. Keep the EXISTING candidate-pool construction unchanged (probes sorted by id, exclude self, string gold → one passage, list gold → each item) so the pool order IS today's id-order. Then:
    - if `embed_fn is None`: return `pool[:n]` exactly as today — byte-identical, no behavior change.
    - if `embed_fn is not None`: inside a try/except, call `ranked = _rank_by_similarity(probe["question"], pool, embed_fn)` and return `ranked[:n]`. On ANY exception, fall back to `pool[:n]` (the id-order result). The function must never raise (preserve the existing outer try/except returning [] as the ultimate guard).

    Tie-break note: because the input `pool` is already id-ordered and Python sort is stable, equal-similarity candidates remain in id order automatically — no extra id key needed, but the pool order must be established BEFORE ranking.

    Follow project style: ruff line-length 100, double quotes, snake_case, `from __future__ import annotations` already present. Keep it minimal — no new module-level constants unless needed.
  </action>
  <verify>
    <automated>.venv/bin/python -m pytest tests/test_bench_grounding.py -q -k "rank_by_similarity or rgb_distractors or hard_neg"</automated>
  </verify>
  <acceptance_criteria>
    - `_rank_by_similarity(query, candidates, embed_fn)` exists, makes exactly one embed_fn call, computes cosine in pure stdlib math, guards zero-norm, returns candidates nearest-first with stable tie-break.
    - `_rgb_distractors` has signature `(probe, probes, n, embed_fn=None)`; embed_fn=None path is byte-identical to today (explicit-list assertion passes).
    - embed_fn provided → topically-nearest candidate returned first; differs from id-order result.
    - embed_fn that raises → returns id-order list; no exception escapes.
    - all-ties embed_fn → deterministic, equals id-order across two calls.
    - New tests pass; no existing test in tests/test_bench_grounding.py regresses.
  </acceptance_criteria>
  <done>_rgb_distractors is embed_fn-aware with byte-identical default and never-raise fallback; _rank_by_similarity is implemented in pure Python; targeted tests green.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Thread embed_fn through RGB axes, add --hard-negatives CLI + hard_negatives output, document the flag</name>
  <files>bench/grounding.py, tests/test_bench_grounding.py</files>
  <behavior>
    Tests (add to tests/test_bench_grounding.py; OFFLINE — monkeypatch g._default_embedder; NO fastembed/sqlite_vec/network):
    - flag present, embedder builds: run main with --mode rgb --hard-negatives, monkeypatch `g._default_embedder` to return a deterministic fake embed_fn; assert out.json has `hard_negatives` == True.
    - flag absent: run main with --mode rgb (no --hard-negatives); assert out.json has `hard_negatives` == False AND distractor behavior is unchanged (id-order) — e.g. spy that `_rank_by_similarity` is NOT invoked, or assert _default_embedder is never called.
    - soft-fail: run main with --mode rgb --hard-negatives but monkeypatch `g._default_embedder` to raise RuntimeError; assert rc == 0, out.json `hard_negatives` == False, and a note mentioning hard-negatives/fastembed is printed (capsys). Harness proceeds id-order.
    - backward-compat: existing test_run_rgb_end_to_end_emits_per_axis_json and test_mode_layers_default_runs_arm_loop_unchanged still pass (no signature breakage).
    - backward-compat note: keep all three axis-helper calls passing embed_fn so default None preserves today behavior.
  </behavior>
  <action>
    Thread an optional `embed_fn` (default None) through `_rgb_noise`, `_rgb_negative`, and `_rgb_integration` — add `embed_fn=None` to each signature (keyword-only is fine, place after existing params) and pass it into their `_rgb_distractors(...)` call as `embed_fn=embed_fn`. Do NOT touch `_rgb_counterfactual` (it uses no distractors). All three signatures must stay backward-compatible (callers that omit embed_fn get None → today's behavior).

    CLI: in `_build_parser`, add `parser.add_argument("--hard-negatives", action="store_true")` in the RGB flags block (near --mode/--axes/--noise-ratios/--rgb-k). It reuses the existing `--embed-model` arg; do not add a new model arg. It is RGB-mode-only by convention (ignored in layers mode — no enforcement needed since layers mode never reads it).

    In `_run_rgb`: near the top (after parsing axes/ratios/judge_models/k), set `embed_fn = None` and `hard_negatives = False`. If `getattr(args, "hard_negatives", False)`: build `embed_fn = _default_embedder(args.embed_model)` inside try/except — on success set `hard_negatives = True`; on Exception, print a note (e.g. `print(f"note: hard-negatives unavailable, proceeding id-order: {exc}")`) and leave embed_fn=None / hard_negatives=False (soft-fail, harness PROCEEDS). Pass `embed_fn=embed_fn` into every `_rgb_noise(...)`, `_rgb_negative(...)`, and `_rgb_integration(...)` call inside the axis loops. Add `output["hard_negatives"] = hard_negatives` to the RGB output dict (before the `args.out` write so it is persisted). When the flag is absent, embed_fn stays None → distractor selection is byte-identical to today.

    Docstring: in the RGB mode section of the module docstring, add a short line documenting `--hard-negatives` (opt-in; reorders distractors topically-nearest-first via the existing embedder/`--embed-model`; soft-fails to id-order when fastembed is unavailable; RGB-mode only).

    Keep changes surgical and ADD-ONLY. Preserve the layers arm loop entirely. ruff line-length 100, double quotes.
  </action>
  <verify>
    <automated>.venv/bin/python -m pytest tests/ --cov=flowstate --cov-fail-under=80 -q</automated>
  </verify>
  <acceptance_criteria>
    - `_rgb_noise`, `_rgb_negative`, `_rgb_integration` accept `embed_fn=None` and forward it to `_rgb_distractors`; `_rgb_counterfactual` unchanged.
    - `--hard-negatives` store_true flag exists in `_build_parser`; reuses `--embed-model`.
    - `_run_rgb` builds embed_fn via `_default_embedder(args.embed_model)` in try/except when flag set; soft-fails (rc 0, note printed) on failure.
    - RGB JSON contains `hard_negatives`: true only when flag set AND embedder built; false otherwise.
    - Flag absent → byte-identical id-order distractors (existing RGB tests unchanged).
    - Module docstring documents `--hard-negatives`.
    - Full suite passes: `.venv/bin/python -m pytest tests/ --cov=flowstate --cov-fail-under=80 -q` exits 0.
  </acceptance_criteria>
  <done>embed_fn threaded through the three distractor-using axes; --hard-negatives flag wired with soft-fail; hard_negatives recorded in RGB JSON; docstring updated; full coverage gate green.</done>
</task>

</tasks>

<verification>
- `.venv/bin/python -m pytest tests/ --cov=flowstate --cov-fail-under=80 -q` exits 0
- `.venv/bin/ruff check bench/grounding.py tests/test_bench_grounding.py` clean
- `.venv/bin/ruff format --check bench/grounding.py tests/test_bench_grounding.py` clean
- Importing `bench.grounding` succeeds WITHOUT fastembed installed (no eager import added)
- No modification to the layers arm loop in `main()` and no change to `_rgb_counterfactual`
</verification>

<success_criteria>
- Opt-in hard-negative distractor selection works end-to-end via `--mode rgb --hard-negatives`, reordering distractors topically-nearest-first.
- Default (flag absent) RGB distractor output is byte-identical to today.
- Embed/rank failures and a missing fastembed both soft-fail to id-order; the harness never raises and returns rc 0.
- RGB JSON records `hard_negatives` true only when the flag is set AND the embedder was built.
- Tests are fully offline (injected fake embed_fn; monkeypatched `_default_embedder`); coverage and ruff gates pass.
</success_criteria>

<output>
Create `.planning/quick/260619-nfe-add-hard-negative-distractor-selection-t/SUMMARY.md` (and `260619-nfe-SUMMARY.md`) when done, with `status:` frontmatter.
</output>
