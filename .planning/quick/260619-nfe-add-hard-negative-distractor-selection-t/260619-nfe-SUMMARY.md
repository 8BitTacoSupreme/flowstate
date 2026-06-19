---
status: complete
phase: quick-260619-nfe
plan: 01
subsystem: bench
tags: [grounding, rgb, embeddings, cosine-similarity, hard-negatives, fastembed]

requires: []
provides:
  - "_rank_by_similarity: pure stdlib cosine ranking helper for RGB distractor selection"
  - "embed_fn-aware _rgb_distractors with byte-identical default and never-raise fallback"
  - "--hard-negatives CLI flag for RGB mode with soft-fail to id-order"
  - "hard_negatives boolean in RGB JSON output"
affects: [bench, grounding-eval]

tech-stack:
  added: []
  patterns:
    - "opt-in flag gates embedder build in _run_rgb; soft-fail preserves harness availability"
    - "inner try/except in _rgb_distractors isolates rank failures from outer never-raise guard"
    - "pure Python cosine (math module) for in-memory candidate lists — no sqlite_vec here"

key-files:
  created: []
  modified:
    - bench/grounding.py
    - tests/test_bench_grounding.py

key-decisions:
  - "embed_fn=None default preserves byte-identical id-order behavior — no behavioral change unless flag explicitly set"
  - "_rank_by_similarity placed before _rgb_distractors in source; no try/except inside it (caller wraps)"
  - "inner try/except in _rgb_distractors (wrapping _rank_by_similarity) keeps outer [] guard intact"
  - "zip(strict=False) used for cosine dot product to satisfy ruff B905"
  - "hard-neg test uses local probe with 'acks' in question to guarantee keyword match with p4 gold"

requirements-completed: [RGBHN-01]

duration: 22min
completed: 2026-06-19
---

# Quick Task 260619-nfe: Hard-Negative Distractor Selection Summary

**Opt-in `--hard-negatives` flag for RGB mode reorders distractors topically-nearest-first via cosine similarity, with soft-fail to id-order and fully offline tests using injected fake embed_fn.**

## Performance

- **Duration:** ~22 min
- **Started:** 2026-06-19T20:40:00Z
- **Completed:** 2026-06-19T21:02:26Z
- **Tasks:** 2 (TDD: 4 commits — 2 RED, 2 GREEN)
- **Files modified:** 2

## Accomplishments

- `_rank_by_similarity(query, candidates, embed_fn)`: pure stdlib cosine ranking, one embed_fn call, zero-norm guard (`float("-inf")` for zero-vector candidates), stable tie-break via Python's stable sort
- `_rgb_distractors` extended with `embed_fn=None`; None path returns `pool[:n]` byte-identical to today; embed_fn path calls `_rank_by_similarity` in inner try/except, falls back to id-order on any exception
- `_rgb_noise`, `_rgb_negative`, `_rgb_integration` each gain `embed_fn=None` keyword arg, forwarded to `_rgb_distractors`; `_rgb_counterfactual` untouched
- `--hard-negatives` store_true flag in `_build_parser`; reuses `--embed-model`
- `_run_rgb` builds embed_fn via `_default_embedder(args.embed_model)` in try/except when flag set; soft-fail prints note; `output["hard_negatives"] = true|false` persisted to JSON
- Module docstring documents `--hard-negatives` in the RGB section

## Task Commits

Each task was committed atomically (TDD: RED then GREEN):

1. **Task 1 RED: failing tests for _rank_by_similarity + embed_fn-aware _rgb_distractors** - `484b433`
2. **Task 1 GREEN: _rank_by_similarity + embed_fn-aware _rgb_distractors** - `00ab722`
3. **Task 2 RED: failing tests for --hard-negatives flag and hard_negatives JSON key** - `cb67d45`
4. **Task 2 GREEN: thread embed_fn through RGB axes, add --hard-negatives CLI flag** - `831def6`

## Files Created/Modified

- `bench/grounding.py` — added `_rank_by_similarity`, extended `_rgb_distractors` signature, added `embed_fn=None` to three axis helpers, `--hard-negatives` parser flag, soft-fail logic in `_run_rgb`, `hard_negatives` output key, docstring update
- `tests/test_bench_grounding.py` — 8 new offline tests: zero-norm guard, hard-neg nearest-first, byte-identity, never-raise, all-ties determinism (`_rank_by_similarity` direct + `_rgb_distractors` integration), plus 3 end-to-end `_run_rgb` tests (flag present/absent/soft-fail)

## Decisions Made

- `embed_fn=None` default means the None path is byte-identical — no behavioral regression possible without explicit opt-in
- Inner try/except in `_rgb_distractors` (around `_rank_by_similarity` call) isolates rank failures from the outer `except Exception: return []` guard — both layers of never-raise preserved
- Hard-neg test uses a local probe with "acks" in the question (not `_RGB_PROBES_FIXTURE`'s p1) because p1's question doesn't share a keyword with any non-first-in-id-order candidate
- `zip(strict=False)` used for cosine dot product (ruff B905 compliance); list spread `[query, *candidates]` replaces concatenation (ruff RUF005)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed test logic for hard-neg ordering test**
- **Found during:** Task 1 GREEN
- **Issue:** `test_rgb_distractors_hard_neg_nearest_first` used `_RGB_PROBES_FIXTURE`'s p1 probe (question: "default replication factor"), which shares no keyword with p4 gold ("acks=all"). Fake embed_fn keyed on "acks" made query vector orthogonal to p4 gold — cosine = 0, not 1 — so p4 didn't rank first.
- **Fix:** Replaced fixture probe with a local probe whose question contains "acks", matching the p4 gold keyword and producing cosine = 1.0.
- **Files modified:** `tests/test_bench_grounding.py`
- **Committed in:** `00ab722`

**2. [Rule 1 - Bug] Fixed `_rank_by_similarity` test: candidates were dicts, not strings**
- **Found during:** Task 1 GREEN (test design)
- **Issue:** `test_rank_by_similarity_zero_norm_no_raise` passed `[{"gold": "zero-norm doc"}, ...]` as candidates; `_rank_by_similarity` expects `list[str]`.
- **Fix:** Changed candidates to plain strings `["zero-norm doc", "normal doc"]`.
- **Files modified:** `tests/test_bench_grounding.py`
- **Committed in:** `00ab722`

**3. [Rule 1 - Bug] Fixed ruff violations in implementation and tests**
- **Found during:** Task 1 GREEN pre-commit hook
- **Issue:** `[query] + candidates` (RUF005), `zip(q_vec, vec)` without `strict=` (B905), `[local_probe] + list(probes)` (RUF005)
- **Fix:** `[query, *candidates]`, `zip(..., strict=False)`, `[local_probe, *probes]`
- **Files modified:** `bench/grounding.py`, `tests/test_bench_grounding.py`
- **Committed in:** `00ab722`

---

**Total deviations:** 3 auto-fixed (all Rule 1 bugs in test logic and ruff compliance)
**Impact on plan:** All fixes in test correctness or style; implementation unchanged. No scope creep.

## Issues Encountered

None — implementation was straightforward. Test design required one iteration to correctly exercise keyword-based cosine matching.

## Known Stubs

None.

## Self-Check

- `bench/grounding.py` modified: confirmed (git log 831def6)
- `tests/test_bench_grounding.py` modified: confirmed (git log 831def6, cb67d45, 00ab722, 484b433)
- All 4 task commits exist: 484b433, 00ab722, cb67d45, 831def6
- Full suite: 766 passed, 92.19% coverage, ruff clean

## Self-Check: PASSED

---
*Quick Task: 260619-nfe*
*Completed: 2026-06-19*
