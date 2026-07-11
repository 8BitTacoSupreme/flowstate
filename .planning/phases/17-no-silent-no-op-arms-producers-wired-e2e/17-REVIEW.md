---
phase: 17-no-silent-no-op-arms-producers-wired-e2e
reviewed: 2026-07-11T01:39:27Z
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
  warning: 4
  info: 2
  total: 6
status: issues_found
---

# Phase 17: Code Review Report

**Reviewed:** 2026-07-11T01:39:27Z
**Depth:** standard
**Files Reviewed:** 6
**Status:** issues_found

## Summary

The change set wires the producer side of the wiki arm (`bench/distiller.py`), a single
per-arm provisioning entry point (`bench/prepare_fixture.py`), and a fail-loud producer
gate in the eval runner (`bench/compound_eval.py`). The subprocess-never-raises contracts
in `_densify` and the producer wrappers are honored, the module rebind of
`orch.build_context_prefix` is call-time-correct (orchestrator references the name from its
own module global, and it is restored in `finally`), and the report/write_json call sites
match their signatures. Cross-referenced against `flowstate.memory.MemoryStore`,
`flowstate.context_prefix`, and `flowstate.pack.PackResult` — the corpus glob contract
(`**/*.md` under `.planning/codebase/wiki/`) matches the reader.

No BLOCKER-level correctness or security defects were found. However, the phase's own
theme — "no silent no-op arms" — is undercut in two places: the fail-loud gate accepts
zero-byte producer artifacts, and `--mode real` with no bridge exits 0. The distiller also
silently truncates durable knowledge to 20 entries per kind, which directly erodes the
compounding value the wiki arm exists to measure.

## Warnings

### WR-01: Distiller silently caps each article at 20 memory entries

**File:** `bench/distiller.py:130`
**Issue:** `by_kind = {kind: store.get_by_kind(kind) for kind in _ARTICLE_KINDS}` calls
`MemoryStore.get_by_kind()` with its default `limit=20` (confirmed at
`flowstate/memory.py:516`). The module docstring promises to distill "the accumulated
`memory.db`" into "durable wiki knowledge," but any kind with more than 20 entries has its
oldest knowledge silently dropped from the corpus. Across many runs — exactly the
compounding regime this arm measures — the wiki corpus becomes a rolling 20-item window,
not a durable knowledge base. This is a data-completeness defect, not a style issue: the
wiki arm can report "producer present" while measuring a truncated fraction of memory.
**Fix:**
```python
# Pass an explicit high/unbounded limit so distillation is complete, not a head-slice.
by_kind = {kind: store.get_by_kind(kind, limit=100_000) for kind in _ARTICLE_KINDS}
```
(Or add an unbounded path to `get_by_kind`; do not rely on the shared default.)

### WR-02: Fail-loud producer gate accepts empty/zero-byte producer artifacts

**File:** `bench/compound_eval.py:90-100`
**Issue:** `_missing_producer` treats mere existence as "producer present":
`(root / _PACK_PATH).is_file()` for pack, and `has_wiki_md = (root / _WIKI_PATH).is_file()`
plus `any(corpus.glob("**/*.md"))` for wiki. A zero-byte `wiki.md` (or an empty `*.md` in
the corpus, or an empty `repomix-pack.xml`) passes the HAR-02 gate, yet the reader produces
nothing: `_read_wiki_layer` returns `""` for empty content (`flowstate/context_prefix.py:432`),
and empty corpus files contribute no tokens to `_semantic_wiki_layer`. The arm is then
declared present and rendered as a normal report while measuring an empty layer — precisely
the silent no-op this phase is meant to eliminate.
**Fix:**
```python
if required == "pack":
    p = root / _PACK_PATH
    return None if (p.is_file() and p.stat().st_size > 0) else "pack"
if required == "wiki":
    corpus = root / _WIKI_CORPUS_DIR
    has_corpus = corpus.is_dir() and any(
        f.stat().st_size > 0 for f in corpus.glob("**/*.md")
    )
    wiki_md = root / _WIKI_PATH
    has_wiki_md = wiki_md.is_file() and wiki_md.stat().st_size > 0
    return None if (has_corpus or has_wiki_md) else "wiki"
```
(Keep the `except OSError` guard around the `stat()` calls so an odd tree still degrades to
"producer absent" rather than raising.)

### WR-03: `--mode real` with no bridge prints a red message but exits 0

**File:** `bench/compound_eval.py:279-285, 356-398`
**Issue:** The module docstring (lines 20-22) and `_real_loop` claim real mode "fails fast"
when no claude bridge is available "rather than silently degrading." In practice
`_real_loop` returns an empty scorecard, and `main()` proceeds to render a report and
`return 0`. A caller scripting the arm matrix (`prepare_fixture` then `compound_eval` per
arm, checking `$?`) sees success for a run that measured nothing. This is inconsistent with
the sibling gate, which returns `_EXIT_PRODUCER_ABSENT` (3) for an absent producer. Both are
"the arm measured nothing," but one exits non-zero and the other exits 0. The unit test
(`test_real_loop_refuses_without_bridge`) only asserts the empty scorecard, never the exit
code, so the process-level silent-success is untested.
**Fix:** Have `main()` detect the refused/empty real-mode run and return a non-zero exit
(mirror the producer gate), e.g.:
```python
if args.mode == "real":
    scorecard, judged = _real_loop(...)
    if not scorecard.snapshots:
        return _EXIT_PRODUCER_ABSENT  # or a dedicated _EXIT_NO_BRIDGE
```
Add an assertion on the return code to the corresponding test.

### WR-04: Distiller corpus write is unguarded despite "Never raises" contract

**File:** `bench/distiller.py:91, 170-172`
**Issue:** `main()`'s docstring states "Never raises," and every earlier step (store read,
densify subprocess) is wrapped. The final write is not: `corpus_dir.mkdir(...)` and
`(corpus_dir / filename).write_text(text)` will propagate `OSError` (read-only FS,
permission, or a file where the corpus dir is expected). On the standalone `__main__` path
(`sys.exit(main())`, line 178) this yields a traceback rather than a reported failure,
breaking the stated contract. `prepare_fixture._run_wiki_producer` happens to wrap the call,
which masks it in that path but not when the distiller is invoked directly.
**Fix:**
```python
try:
    corpus_dir.mkdir(parents=True, exist_ok=True)
    for filename, text in written.items():
        (corpus_dir / filename).write_text(text)
except OSError as exc:
    print(f"distiller: could not write corpus under {corpus_dir}: {exc}", file=sys.stderr)
    return 1
```

## Info

### IN-01: Distiller reaches into another module's private symbol

**File:** `bench/distiller.py:30`
**Issue:** `from bench.judge import _locate_claude` imports a leading-underscore private from
a sibling bench module. This couples the distiller to `judge.py`'s internal API; a rename
there breaks the distiller silently (no public contract). `_bridge_available` in
`compound_eval.py` deliberately re-implements the locator with stdlib to stay decoupled —
the two approaches are inconsistent.
**Fix:** Promote a shared `locate_claude()` (public) in one place (e.g. `bench/judge.py` or a
small `bench/_claude.py`) and import that from both callers.

### IN-02: Article filenames produce ungrammatical plurals

**File:** `bench/distiller.py:56`
**Issue:** `f"{index:02d}-{kind.value}s.md"` yields `03-researchs.md` and `04-strategys.md`
for the RESEARCH/STRATEGY kinds. Deterministic and harmless to the `**/*.md` reader, but the
filenames read as defects to a human inspecting the corpus.
**Fix:** Use a small kind→noun map (e.g. `{RESEARCH: "research", STRATEGY: "strategy", ...}`)
or drop the trailing `s` to keep singular kind names.

---

_Reviewed: 2026-07-11T01:39:27Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
