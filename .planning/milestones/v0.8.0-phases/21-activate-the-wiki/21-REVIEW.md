---
phase: 21-activate-the-wiki
reviewed: 2026-07-11T00:00:00Z
depth: standard
files_reviewed: 7
files_reviewed_list:
  - flowstate/distiller.py
  - bench/distiller.py
  - flowstate/cli.py
  - flowstate/context_prefix.py
  - flowstate/context.py
  - flowstate/orchestrator.py
  - flowstate/state.py
findings:
  critical: 0
  warning: 2
  info: 3
  total: 5
status: clean
---

# Phase 21: Code Review Report

**Reviewed:** 2026-07-11
**Depth:** standard
**Files Reviewed:** 7
**Status:** issues_found

## Summary

Phase 21 wires the memory→wiki distiller into production (`flowstate/distiller.py` +
`flowstate distill` CLI) and activates the dormant Phase-11 semantic wiki layer behind an
opt-in `wiki_layer` flag. I verified all six load-bearing contracts and they hold:

1. **Byte-identity (contract 1) — HOLDS.** Flag off ⇒ `orchestrator.py:257` sets
   `_wiki_include_layers = None`, and the new call passes `include_layers=None`, which is
   the historical default. All new logic in `build_context_prefix` lives inside the
   `if wiki_included:` block, which the default path never enters. No default-path
   regression. No BLOCKER.
2. **The `_STANDARD_LAYERS ∪ {"wiki"}` union (contract 2) — HOLDS.** `_STANDARD_LAYERS =
   frozenset({"fixtures","pack","gotchas","memory","since_last_run"})` matches the five
   `_included(...)` keys exactly (verified by grep). The orchestrator passes the union, not
   `{"wiki"}` alone. No BLOCKER.
3. **Packaging (contract 3) — HOLDS.** `flowstate/distiller.py` imports nothing from
   `bench/`; `_locate_claude` delegates to `bridge._find_claude` with `return found or None`
   (""→None). `import flowstate.distiller` resolves with `bench` popped from `sys.modules`.
   `bench/distiller.py` is a re-export shim.
4. **Never-raise / graceful-degrade (contract 4) — HOLDS.** Distiller wraps memory read and
   corpus write; fails loud (rc=1) on empty memory. `get_embedder` never returns None but
   `available()` returns False without fastembed, so the WIKI-05 warning gate
   (`not emb.available()`) fires correctly and the run continues.
5. **D-03 scope fence (contract 5) — HOLDS.** Orchestrator change is isolated to the single
   `build_context_prefix` call site; no distiller auto-invocation in `run_pipeline`.
6. **Staleness (contract 6) — HOLDS with one gap.** `is_wiki_stale` keys on `memory.db`
   mtime vs manifest `created_at`, mirroring `is_pack_stale`; `_register` correctly skips
   the checksum for the `"wiki"` directory kind. The gap is that neither helper checks
   whether the artifact still exists on disk (WR-01 below).

Two Warnings and three Info items follow. No Critical findings.

## Warnings

### WR-01: `is_wiki_stale` reports "up to date" for a deleted corpus, so `flowstate distill` refuses to regenerate it

**File:** `flowstate/distiller.py:114-122` (consumed at `flowstate/cli.py:824`)
**Issue:** `is_wiki_stale` only compares `memory.db` mtime against the manifest entry's
`created_at`. It never checks whether the corpus directory (or any `*.md` inside it) still
exists. If a user deletes `.planning/codebase/wiki/` (plausible — it lives under a
frequently-cleaned `.planning/codebase/` tree) and `memory.db` is unchanged, the manifest
entry persists, `is_wiki_stale` returns `False`, and the CLI prints
"Wiki corpus up to date; skipping" and does no work. The wiki layer then silently
contributes nothing on the next run. This is worse than the mirrored `is_pack_stale` case
because the wiki corpus is a directory of many files, any subset of which can go missing.
Because the CLI always passes `--force` to the distiller, the distiller's own
`corpus_dir.is_dir()` guard never compensates — the CLI's `is_wiki_stale` gate is the sole
decision-maker.
**Fix:** Treat an absent corpus as stale:
```python
def is_wiki_stale(root: Path, state) -> bool:
    entry = next((e for e in state.install_manifest if e.path == _WIKI_CORPUS_REL), None)
    if entry is None:
        return True

    corpus_dir = root / _WIKI_CORPUS_REL
    if not corpus_dir.is_dir() or not any(corpus_dir.glob("**/*.md")):
        return True  # entry present but corpus gone — regenerate

    memory_db = root / "memory.db"
    if not memory_db.exists():
        return False
    return memory_db.stat().st_mtime > entry.created_at.timestamp()
```

### WR-02: distiller never clears the corpus dir, so a changed non-empty-kind set leaves orphaned duplicate articles the semantic reader ingests

**File:** `flowstate/distiller.py:200-214`
**Issue:** Article filenames are numbered by position in `non_empty` (`_article_filename`
uses `enumerate(non_empty.items(), start=1)`). The set of non-empty kinds changes as memory
grows — e.g. run 1 has only INSIGHT (`01-insights.md`); run 2 adds DECISION, so DECISION
becomes `01-decisions.md` and INSIGHT shifts to `02-insights.md`. Step 5 does
`corpus_dir.mkdir(parents=True, exist_ok=True)` and writes only the current `written` dict —
it never removes stale files. The old `01-insights.md` is now orphaned alongside the new
`02-insights.md`. `_semantic_wiki_layer` globs `**/*.md` and appends every non-blank file
with no dedup (`context_prefix.py:261-266`), so the orphan is injected as a **duplicate
article** into the KNN pool, biasing retrieval and wasting budget. This is inherited from
the bench origin but ships in the production module.
**Fix:** Clear the corpus dir before writing the fresh set (build in-memory first, as the
code already does, then replace atomically):
```python
try:
    if corpus_dir.exists():
        shutil.rmtree(corpus_dir)
    corpus_dir.mkdir(parents=True, exist_ok=True)
    for filename, text in written.items():
        (corpus_dir / filename).write_text(text)
except OSError as exc:
    print(f"distiller: could not write corpus under {corpus_dir}: {exc}", file=sys.stderr)
    return 1
```

## Info

### IN-01: `bench/distiller.py` wildcard re-export has no `__all__` in the source module

**File:** `bench/distiller.py:16` / `flowstate/distiller.py`
**Issue:** `from flowstate.distiller import *` with no `__all__` defined in
`flowstate/distiller.py` re-exports every public name in that module's namespace, including
incidental imports (`Path`, `MemoryKind`, `MemoryStore`, `PROMPT_HEADER`) that are not part
of the intended distiller API. The explicit import block below it already names the seven
symbols tests need, so the wildcard adds only namespace pollution.
**Fix:** Either drop the `import *` line (the explicit block is sufficient) or add
`__all__` to `flowstate/distiller.py` to bound the wildcard surface.

### IN-02: `_ARTICLE_KINDS` includes `MemoryKind.RUN` (run-journal deltas) as "durable" wiki knowledge

**File:** `flowstate/distiller.py:36-42`
**Issue:** The comment justifies excluding `TOOL_RUN` as "ephemeral run-log noise," yet the
list includes `MemoryKind.RUN` ("run"), which `context_prefix._read_since_last_run_layer`
describes as "run-journal deltas … most dynamic." Distilling per-run journal entries into
the durable wiki corpus is arguably the same ephemerality the comment claims to avoid, and
lets a project whose memory holds only RUN entries produce a wiki of run-log noise (the
fail-loud guard only trips when *all* kinds are empty). This is a deliberate carry-over from
the bench distiller, so confirm it is intentional rather than a copy of the wrong constant.
**Fix:** If RUN journal entries are not durable knowledge, drop `MemoryKind.RUN` from
`_ARTICLE_KINDS`; otherwise update the comment to explain why RUN (but not TOOL_RUN) counts
as durable.

### IN-03: `_densify` returns un-stripped subprocess stdout

**File:** `flowstate/distiller.py:95-97`
**Issue:** The densify success path returns `proc.stdout` verbatim (only `.strip()`-tested,
not stripped), so a trailing newline from `claude --print` is written into the article,
whereas the deterministic `_render_article` path is clean. Purely cosmetic — surfaces as
trailing whitespace in an article joined by `_SEPARATOR`.
**Fix:** `return proc.stdout.strip()` on the success branch for parity with the
deterministic path.

---

_Reviewed: 2026-07-11_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
