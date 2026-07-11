---
id: 260711-research-grounding-fix
type: quick
status: complete
subsystem: research-adapter, bench-verdict
tags: [research, groundedness, fail-open, bench, verdict, phase-22, grounding]
requires: [flowstate.state, flowstate.pack, flowstate.bridge, bench.project]
provides: [bench.ground.ground_from_repo, research-fail-open-scoring]
affects: [flowstate/tools/research.py, bench/verdict.py, 22-PREREGISTRATION.md]
key-files:
  created:
    - bench/ground.py
    - tests/test_ground.py
  modified:
    - flowstate/tools/research.py
    - tests/test_research_grounding.py
    - bench/verdict.py
    - .planning/phases/22-the-verdict/22-PREREGISTRATION.md
decisions:
  - "Scorer-unavailable sentinel is None (float|None), NOT 0.0 -- fail OPEN, keep the section"
  - "Scorer br.error captured on self._last_scorer_error so execute can surface it (return type stays float|None per acceptance criteria)"
  - "ground_from_repo is a one-time --root setup gate, guarded to mode==real, never per-trial"
  - "Preregistration section 8 is setup-only -- frozen win rule / arms / n unchanged"
metrics:
  duration: ~7 min
  completed: 2026-07-11
  tasks: 3
  commits: 3
  tests_added: 15
---

# Quick Task 260711: Research Grounding Fix Summary

Two locked fixes ahead of the Phase-22 paid verdict: (2) research groundedness scoring now
fails OPEN and observable -- a down/unparseable scorer keeps the section instead of silently
discarding it as 0.0; and (1) a new `bench/ground.py::ground_from_repo` auto-derives a repo
interview via ONE bounded `claude --print` call + repomix pack, wired as a one-time real-mode
setup step in the verdict so every arm plans the REAL subject repo.

## What Changed

### Task 1 -- Research groundedness fail-open + observable (`flowstate/tools/research.py`)
- `_score_groundedness` return type is now `float | None`. Returns `None` (the
  *scorer-unavailable* sentinel) when the scoring bridge call fails **or** the json-mode output
  carries no clean integer -- no longer falls through to `0.0`. The scorer `br.error` is captured
  on `self._last_scorer_error` so `execute` can surface an attributable reason.
- `execute` now has a three-way outcome: `kept` / `discarded-low-score` / `scorer-unavailable ->
  KEPT`. A `None` score keeps the section (fail-open, mirroring the existing "no questions -> keep
  all" philosophy), records the topic in a distinct `scorer_unavailable_topics` bucket, and
  short-circuits the retry loop. A scorer that goes down mid-retry also keeps the regenerated
  section.
- The `## Groundedness` report block adds a `Scorer-unavailable (kept): ...` line distinct from
  `Discarded:`. The `produced == 0` `ToolResult.error` appends a distinct
  `scorer-unavailable: {topics} ({br.error})` clause so an empty report is attributable.
- `0.6` threshold, `_load_retrieval_questions`, and the retrieval_questions criterion unchanged.

### Task 2 -- `bench/ground.py` auto-derive repo grounding (new)
- `ground_from_repo(root) -> InterviewAnswers`: reads a bounded README slice + a cheap structural
  summary (prefers an existing repomix pack excerpt, else a shallow one-level walk -- no full-tree
  crawl), makes ONE `ClaudeBridge.run(output_format="json", allowed_tools=[], max_turns=2,
  model="sonnet")` call, parses STRICT JSON into `InterviewAnswers`, writes it into
  `flowstate.json` via `load_state`/`save_state`, then guards repomix and runs `run_pack`.
- Fails LOUD (RuntimeError) on a failed bridge call, unparseable derivation JSON, or an absent
  repomix binary (install hint) -- never writes garbage state or silently continues.
- `python -m bench.ground --root <repo>` CLI entry: exit 0 on success, 1 on failure.
- The unrelated `bench/grounding.py` (RGB/promptab benchmark) is untouched.

### Task 3 -- Wire grounding into the verdict + preregistration addendum
- `bench/verdict.py::main` imports `ground_from_repo` and calls it ONCE in real-mode setup
  (guarded to `args.mode == "real"`), before `_collect`, so the grounded `flowstate.json` + pack
  are frozen on `--root` and every `_worktree` copy inherits them via `scaffold(synthetic=False)`.
  Cheap mode never calls it (stays deterministic + free).
- `22-PREREGISTRATION.md` section 8 setup addendum documents the auto-grounding step and states
  EXPLICITLY it does NOT change the frozen D-02 decision rule (CI-excludes-0 AND d>=0.8 AND
  Holm-reject), the 5 arms, or n.
- A preservation test asserts `scaffold(synthetic=False)` keeps the grounded interview + pack
  while wiping `memory.db`.

## Tests
- `tests/test_research_grounding.py`: +7 (bridge-failure->None, unparseable->None, clean "7"->0.7,
  scorer-unavailable keeps section, distinct-from-discarded, produced==0 kept-on-scorer-down,
  mixed produced==0 error text). Bridge is `MagicMock`, no real LLM.
- `tests/test_ground.py`: +8 (interview populated, pack-once, repomix-absent fails loud,
  unparseable JSON fails loud, bridge-failure fails loud, main exit 0/1, scaffold preservation).
  Derivation bridge + `run_pack` + `_find_repomix` all mocked -- no real LLM/repomix.

## Verification
- `uv run python -m pytest tests/ -q` -> 1234 passed, 1 skipped, **91.21%** coverage (>=80% gate).
- `uv run ruff check .` -> all checks passed.
- `uv run python -m bench.verdict --mode cheap --root .` -> exit 0 (grounding NOT invoked in cheap).
- No new runtime dependencies (stdlib + flowstate/bench only).

## Deviations from Plan
- **[Interface reconciliation]** The plan's Task-1 action said to "capture the scorer
  `br.error`" while the acceptance criteria fixed the return type at `float | None`. To satisfy
  both, `_score_groundedness` returns `float | None` (as the acceptance criteria + the direct unit
  tests require) and stashes the error on `self._last_scorer_error` for `execute` to read, rather
  than widening the return to a tuple. No behavioral difference; both contracts met.

Otherwise executed exactly as written.

## Self-Check: PASSED
- `bench/ground.py` -- FOUND
- `tests/test_ground.py` -- FOUND
- Commits eccf4fd, f4cbdcc, 2b50b86 -- FOUND
