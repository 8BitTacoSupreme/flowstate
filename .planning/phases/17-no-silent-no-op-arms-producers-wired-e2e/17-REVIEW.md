---
phase: 17-no-silent-no-op-arms-producers-wired-e2e
reviewed: 2026-07-11T02:00:00Z
depth: standard
files_reviewed: 6
files_reviewed_list:
  - bench/compound_eval.py
  - bench/distiller.py
  - bench/prepare_fixture.py
  - tests/test_bench_compound.py
  - tests/test_bench_distiller.py
  - tests/test_bench_prepare_fixture.py
findings:
  critical: 0
  warning: 0
  info: 3
  total: 3
status: issues_found
---

# Phase 17: Code Review Report (Re-Review)

**Reviewed:** 2026-07-11
**Depth:** standard
**Files Reviewed:** 6
**Status:** issues_found (info-only; no blockers or warnings remain)

## Summary

Re-review after four warning-level fixes (WR-01..WR-04) were applied to the Phase-17
bench arm-producer wiring. I verified each fix against the current source, cross-checked
the reader-side contracts in `flowstate/context_prefix.py` and `flowstate/memory.py`, and
ran the three affected test files (78 passed).

**All four warnings are genuinely resolved — not superficially patched.** The two
changes flagged for scrutiny (WR-03's exit-code control flow, WR-02's `stat()` guard)
introduce no new correctness or security defects. The two prior INFO items (IN-01 private
`_locate_claude` import, IN-02 `researchs`/`strategys` filenames) were intentionally
deferred and remain present. One additional low-severity robustness note (IN-03) surfaced
in the WR-04 write path.

### Fix verification

- **WR-01 (RESOLVED).** `bench/distiller.py:134` calls
  `store.get_by_kind(kind, limit=100_000)`. Confirmed `MemoryStore.get_by_kind`
  (`flowstate/memory.py:516`) takes a keyword-only `limit` (default 20), so the explicit
  high limit is valid and defeats the head-slice. `test_distills_more_than_default_limit_entries`
  (50 entries) passes — every summary appears, none dropped.

- **WR-02 (RESOLVED).** `_missing_producer` (`bench/compound_eval.py:82-116`) now requires
  `stat().st_size > 0` for the pack and for `wiki.md`, and >=1 non-empty `*.md` for the
  corpus, all under a single `except OSError` guard that degrades to "producer absent."
  Cross-checked the reader: `_semantic_wiki_layer` globs `**/*.md` (context_prefix.py:250) —
  the identical recursive pattern to the gate, so there is no depth-mismatch no-op. The
  single-file `wiki.md` fallback the gate accepts is genuinely read by `_read_wiki_layer`
  (context_prefix.py:514-515), so accepting either producer is correct. Zero-byte,
  odd-tree, and both-satisfied cases are covered by tests.

- **WR-03 (RESOLVED, no new defect).** `_EXIT_NO_BRIDGE = 4` (line 62); `main()` returns it
  at lines 384-385 when a real-mode scorecard has no snapshots. Traced the control flow:
  `runs = max(1, args.runs)` guarantees >=1 iteration, and `_real_loop` appends a snapshot
  after the per-run try/except on every iteration when the bridge is available — so an empty
  `scorecard.snapshots` in real mode occurs *only* on the bridge-refusal path. The early
  return correctly skips report rendering and `--out` (the arm measured nothing) while
  `_real_loop` has already printed the red refusal message. The producer gate still runs
  first (returns 3), so the two non-zero exits do not collide.
  `test_main_real_mode_without_bridge_returns_nonzero` confirms rc == 4.

- **WR-04 (RESOLVED).** `bench/distiller.py:177-183` wraps the corpus `mkdir` + write loop
  in `try/except OSError`, returning 1 with a stderr message instead of a traceback.
  `test_unwritable_corpus_dir_returns_nonzero_without_raising` exercises the
  `NotADirectoryError` path. See IN-03 for a minor residual on partial writes.

## Info

### IN-01: Private symbol imported across bench modules

**File:** `bench/distiller.py:30`
**Issue:** `from bench.judge import _locate_claude` imports a leading-underscore (private)
symbol from a sibling module. Fragile coupling — a rename in `bench/judge.py` breaks the
distiller silently. Intentionally deferred in the prior review; re-listed for completeness.
**Fix:** Promote the locator to a public helper (e.g. `bench.judge.locate_claude`) or move
the shared locator into a small `bench/_claude.py` utility imported by both.

### IN-02: Pluralized filenames are grammatically wrong

**File:** `bench/distiller.py:56`
**Issue:** `_article_filename` produces `{kind.value}s.md`, yielding `03-researchs.md` and
`04-strategys.md` for `MemoryKind.RESEARCH` / `MemoryKind.STRATEGY`. Harmless to the reader
(globs `*.md`) but visibly wrong in the corpus. Intentionally deferred; re-listed.
**Fix:** Use a small plural map or drop the trailing `s` (the numeric prefix + kind value
is already unique): `f"{index:02d}-{kind.value}.md"`.

### IN-03: WR-04 write loop can leave a partial corpus on a mid-loop OSError

**File:** `bench/distiller.py:165-183`
**Issue:** The comment at lines 165-166 states the in-memory build ensures "a mid-loop
failure never leaves a half-written corpus on disk." That guarantee holds for the
render/densify loop only. The subsequent write loop (lines 179-180) writes files one at a
time; an `OSError` on the second file (e.g. disk full) after the first `write_text`
succeeds leaves a partial corpus AND returns 1. Low impact — `prepare_fixture` propagates
the non-zero rc and halts the matrix, so a later `_missing_producer` gate is not reached in
the same run — but the docstring claim overstates the guarantee, and a partial corpus left
on disk could satisfy a *subsequent* invocation's gate if an operator ignores the non-zero
exit. Related: the `limit=100_000` magic cap from the WR-01 fix (line 134) would still
silently truncate any kind with >100k entries; acceptable given the comment, noted only for
completeness.
**Fix:** Write to a temp sibling dir and atomically `os.replace` into place, or delete the
files written so far in the `except OSError` branch before returning 1; and narrow the
line 165-166 comment to the render phase it actually covers.

---

_Reviewed: 2026-07-11_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
