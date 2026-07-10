---
phase: quick-260710-ffo
plan: 01
status: complete
subsystem: testing
tags: [bench, benchmarking, docs, retrieval, harness-value, integrity]

requires: []
provides:
  - "bench/BENCHMARKING_SCOPE.md — two-track benchmark model (Track 1 retrieval-ranking vs Track 2 harness-value)"
  - "bench/PAIRED_DESIGN_RUNBOOK.md corrected — #1/#2 marked LANDED with file:line refs, #3 the only unbuilt item"
  - "cross-links between BENCHMARK_HANDOFF.md, BENCHMARKING_SCOPE.md, PAIRED_DESIGN_RUNBOOK.md"
affects: [bench-suite, benchmarking-record, v0.7.0-milestone-context]

tech-stack:
  added: []
  patterns: ["docs-only quick task — no .py/test/pyproject.toml changes"]

key-files:
  created:
    - bench/BENCHMARKING_SCOPE.md
  modified:
    - bench/PAIRED_DESIGN_RUNBOOK.md
    - bench/BENCHMARK_HANDOFF.md

key-decisions:
  - "Preserved the original 'Prerequisite code changes' proposal text as a collapsed <details> historical block rather than deleting it, per plan instruction to preserve still-valid content and mark supersession inline."
  - "Kept the original pack-gain expectation sentence with strikethrough + SUPERSEDED annotation rather than removing it, so the correction is traceable against the original claim."

requirements-completed: [FFO-DOC-01, FFO-DOC-02]

duration: ~20min
completed: 2026-07-10
---

# Quick Task 260710-ffo: Correct Benchmarking Record Summary

**Created the authoritative two-track benchmark model (bench/BENCHMARKING_SCOPE.md) and corrected the stale PAIRED_DESIGN_RUNBOOK.md so a retrieval-vs-harness category error, and re-derivation of already-landed work, cannot recur.**

## Performance

- **Duration:** ~20 min
- **Tasks:** 2 (both `type="auto"`, docs-only)
- **Files modified:** 3 (1 created, 2 edited)

## Accomplishments

- `bench/BENCHMARKING_SCOPE.md` created in the house style of `BENCHMARK_HANDOFF.md` (measured-not-estimated, `file:line` citations, terse tables, integrity-rules section). States Track 1 (retrieval component: `bench/longmemeval.py`, `bench/locomo.py`, `bench/_retrieval.py` — zero LLM, deterministic) vs Track 2 (harness value: `bench/compound_eval.py`, `bench/replicate.py`, `bench/metrics.py`, `bench/judge.py`, `bench/report.py` — output-quality per token). Records the honest NULL harness result, the absence of any token/cost/latency accounting (`prefix_tokens` is a `len()//4` estimate, `BridgeResult` has no `usage` field), the unenforced evaluator independence (`judge.py` shells to `claude` directly, bypassing `flowstate.bridge`), and debunks the dead-alias trio (`autoresearch`/`gstack`/`superpowers`) as deleted-on-migration state keys — not a persuasion/trust-boundary architecture.
- `bench/PAIRED_DESIGN_RUNBOOK.md` corrected in place: prerequisite #1 (`--layers` toggle, `bench/compound_eval.py:60-66`) and #2 (`--paired` normalization, `bench/replicate.py:60-67`, `:100-106`) marked **LANDED** with a note that the shipped implementation (first-class `include_layers` kwarg) is better than the originally proposed post-hoc heading filter, which is preserved as a collapsed historical block. #3 (multi-judge) marked **STILL UNBUILT**, pointing at `bench/grounding.py:1136`'s `--judge-models` pattern to copy. The stale "pack/RAG has most of the gain" expectation is struck through and annotated SUPERSEDED, with a new section citing the measured 0.825 ≈ oracle 0.800 wiki result (17/20 vs BM25's 3/20). The WIKI-F1 gap is flagged honestly: no production caller passes `include_layers={"wiki"}`, no corpus exists on disk, and there's a single-file (`wiki.md`) vs article-directory (`.planning/codebase/wiki`) mismatch between `bench/wikigen.py` and the Phase-11 semantic retriever (`flowstate/context_prefix.py:54,64`). All still-valid content preserved: attribution logic, cost reality, verdict rules, upgrade path.
- All three bench docs now cross-link: `BENCHMARK_HANDOFF.md` gained a one-line pointer to `BENCHMARKING_SCOPE.md` and `PAIRED_DESIGN_RUNBOOK.md`; `PAIRED_DESIGN_RUNBOOK.md` gained a "See also" line pointing back to both; `BENCHMARKING_SCOPE.md`'s header cross-links to both.

## Task Commits

Each task was committed atomically:

1. **Task 1: Create bench/BENCHMARKING_SCOPE.md** - `9790284` (docs)
2. **Task 2: Fix PAIRED_DESIGN_RUNBOOK.md and add BENCHMARK_HANDOFF.md pointer** - `c268cc9` (docs)

## Files Created/Modified

- `bench/BENCHMARKING_SCOPE.md` (created) — two-track model, dead-alias debunk, integrity rules.
- `bench/PAIRED_DESIGN_RUNBOOK.md` (modified) — landed-status corrections, superseded pack-gain expectation, WIKI-F1 gap, cross-links.
- `bench/BENCHMARK_HANDOFF.md` (modified) — one-line pointer added after the date line.

## Decisions Made

- Preserved the original "Prerequisite code changes" proposal text as a collapsed `<details>` block instead of deleting it — keeps the historical record auditable while making the LANDED status unambiguous at a glance.
- Kept the original "most quality gain... comes from the pack/RAG" sentence with strikethrough + SUPERSEDED annotation rather than deleting it, so future readers can see exactly what was corrected and why (traceable against the measured 0.825 wiki result).

## Deviations from Plan

None — plan executed exactly as written. All quantitative claims cited in the plan were independently re-verified against source before writing (`compound_eval.py:60-66`, `replicate.py:60-67`, `replicate.py:100-106`, `grounding.py:1136`, `state.py:63-65`, `test_state.py:92-94`, `discipline.py:1`, `memory.py:44,618`, `bridge.py:16,105-109,197,230`, `metrics.py:51`, `capture.py:186`, `report.py:80`, `context_prefix.py:54,64`, `verify.py:57-129`) — no re-derivation, no contradiction.

## Issues Encountered

- **Worktree cwd drift (issue class #3097/#3099):** several early commands used `cd /Users/jhogan/frameworx` (the main repo path, not the worktree at `.../.claude/worktrees/agent-a840dc6a232dc53fc`), and the first `Write` call for `bench/BENCHMARKING_SCOPE.md` used an absolute path that resolved into the main repo instead of the worktree. Caught before any commit: `git status --short` on the worktree showed no pending change while the main repo showed an untracked/staged file. Recovery: unstaged and removed the mis-placed file from the main repo (`git reset HEAD -- ...` + `rm`, leaving the main repo exactly as it was before — only the pre-existing unrelated untracked `repomix-pack.xml` remained), then recreated the file at the correct worktree-absolute path and re-ran all verification/staging/commit steps with `git rev-parse --show-toplevel` confirmed against the worktree root before every subsequent write and commit. No data was lost; no commit was made against the wrong repo.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- The benchmarking record is now internally consistent: a reader can tell Track-1 retrieval-ranking claims from Track-2 harness-value claims, and the runbook no longer instructs re-building already-shipped `--layers`/`--paired` support.
- Remaining open item per the runbook: `bench/judge.py` multi-judge support (port `bench/grounding.py:1136`'s `--judge-models` pattern) before the next real-repo paired-design run.
- Remaining open item per `.planning/STATE.md`: WIKI-F1 (no production caller for `include_layers={"wiki"}`, no `.planning/codebase/wiki/` corpus on disk) is out of scope for this docs-only task and remains deferred.
- No blockers for downstream work; this task touched only `bench/*.md`.

---
*Quick task: 260710-ffo*
*Completed: 2026-07-10*
