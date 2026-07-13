---
phase: 21-activate-the-wiki
verified: 2026-07-11T00:00:00Z
status: passed
score: 8/8 must-haves verified
overrides_applied: 0
re_verification:
  previous_status: none
  previous_score: n/a
---

# Phase 21: Activate the Wiki Verification Report

**Phase Goal:** The proven-best context layer (distilled wiki + semantic retrieval) stops sitting dormant and actually fires on production runs, with the default path staying byte-identical when the flag is off.
**Verified:** 2026-07-11
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | WIKI-03 D-01: distiller is a production module importing NOTHING from bench/ (wheel-safe); bench re-exports it | ✓ VERIFIED | `flowstate/distiller.py:28-29` imports only `flowstate.bridge`/`flowstate.memory`; `grep -c bench = 0`; `import flowstate.distiller` with `bench` popped from sys.modules exits 0; `bench/distiller.py` is a `from flowstate.distiller import *` + explicit re-export shim with `__all__` |
| 2 | WIKI-03 D-02: `flowstate distill` CLI works with --force/--llm/--model | ✓ VERIFIED | `flowstate/cli.py:796-842` `@main.command("distill")`; `flowstate distill --help` lists --force/--llm/--model; staleness-gated skip → `distiller.main` → `_register(kind="wiki")` → `save_state` |
| 3 | WIKI-03 D-04: kind="wiki" manifest + is_wiki_stale keyed on memory.db mtime; WR-01 fix (missing/empty corpus = stale) | ✓ VERIFIED | `state.py:59` Literal gains "wiki"; `context.py:38` checksum skip `kind not in {"memory","wiki"}`; `distiller.py:100-131` `is_wiki_stale` compares memory.db mtime vs entry.created_at AND returns True when corpus dir absent or has no `**/*.md` (WR-01, lines 118-125) |
| 4 | WIKI-03: WR-02 fix (distiller clears stale articles before writing); never-raise + fail-loud-on-empty preserved | ✓ VERIFIED | `distiller.py:231-233` unlinks top-level `*.md` before writing fresh set; empty memory → `rc=1` no files (lines 189-195); write wrapped in try/except OSError → rc=1 (lines 220-238); read errors → rc=1 w/ store.close() in finally |
| 5 | WIKI-04 D-05/D-06: flag off ⇒ include_layers=None ⇒ byte-identical; flag on ⇒ _STANDARD_LAYERS ∪ {"wiki"} (union matches the five real _included keys) | ✓ VERIFIED | `orchestrator.py:257` `_STANDARD_LAYERS \| {"wiki"} if state.preferences.wiki_layer else None`; `context_prefix.py:74` `_STANDARD_LAYERS={"fixtures","pack","gotchas","memory","since_last_run"}` matches EXACTLY the 5 live `_included(...)` calls (line 545 is a comment, not a call); byte-identity regression test passes |
| 6 | WIKI-05 D-07: flag on + [semantic] absent ⇒ single get_embedder probe, one-time warning naming `pip install flowstate[semantic]`, never crash | ✓ VERIFIED | `context_prefix.py:551` single `emb = get_embedder(root)` reused for retrieval + gate; `_warn_semantic_absent` (line 430) guarded by module sentinel `_semantic_warning_emitted` (line 81), fires once; degrades to `_read_wiki_layer`, never raises |
| 7 | WIKI-06 D-08: dogfood asserts layer FIRES (corpus globbed + top-k content in prefix); acceptance = fires, not quality | ✓ VERIFIED | `tests/test_wiki_dogfood.py` asserts `## Codebase Wiki` heading + distinctive article line in prefix via `_STANDARD_LAYERS \| {"wiki"}`; no score asserted; accepts semantic OR static path. See WIKI-06 assessment below. |
| 8 | D-03 scope fence: run_pipeline NOT auto-wired to distill | ✓ VERIFIED | `grep distill flowstate/orchestrator.py` → no distiller import or invocation; only the `build_context_prefix` call site (line 258) changed |

**Score:** 8/8 truths verified

### WIKI-06 Assessment (honest appraisal per verification instructions)

WIKI-06's literal text says the dogfood runs "using this project's `memory.db`." This project's real `memory.db` (73 KB, present) has **0 distillable rows** across all five `_ARTICLE_KINDS` (decision/insight/research/strategy/run — confirmed by direct query), so `test_wiki_layer_fires_on_real_memory` correctly **SKIPS** with an explicit reason — which D-08 explicitly sanctions ("if neither semantic nor any corpus can be produced, skip with an explicit reason rather than fail").

The "layer fires" proof therefore rests on the executor-added `test_wiki_layer_fires_end_to_end`, a synthetic 2-entry (DECISION+INSIGHT) seed that exercises the **exact production functions** — `distiller.main(--force)` → `build_context_prefix(..., include_layers=_STANDARD_LAYERS | {"wiki"})` — and asserts firing (heading + injected article content) on every run. In this environment the embedder is available, so it fires through the real **semantic KNN** path, not a mock.

**Judgment: acceptable satisfaction, not a gap.** The synthetic guard exercises identical production wiring with the identical union; the only deviation from the literal spec is the data source. Critically, a test that *only* skips (as the literal D-08 would here) cannot function as the dormancy regression guard the phase goal requires — the synthetic addition closes that hole and is a strengthening, not a workaround. The real-memory assertion auto-activates the moment `memory.db` accumulates any distillable entry. WIKI-06's intent — "the layer demonstrably fires through production wiring" — is genuinely met.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `flowstate/distiller.py` | Production distiller, imports nothing from bench | ✓ VERIFIED | `def main(`, `_WIKI_CORPUS_REL`, `is_wiki_stale`, `_locate_claude`→bridge; 0 bench imports |
| `bench/distiller.py` | Re-export shim | ✓ VERIFIED | `from flowstate.distiller import *` + explicit 7-symbol re-export + `__all__` |
| `flowstate/cli.py` | `flowstate distill` command | ✓ VERIFIED | Lines 796-842, staleness-gated, manifest-tracked |
| `flowstate/context_prefix.py` | `_STANDARD_LAYERS` + one-time warning | ✓ VERIFIED | Line 74 constant, line 430 `_warn_semantic_absent` |
| `flowstate/orchestrator.py` | Flag-gated union at call site | ✓ VERIFIED | Line 257-260, D-03 fence intact |
| `flowstate/state.py` | `wiki_layer` flag + kind Literal | ✓ VERIFIED | Line 51 flag default False, line 59 Literal gains "wiki" |
| `tests/test_wiki_dogfood.py` | Dogfood firing proof | ✓ VERIFIED | 2 integration/slow tests + `_assert_wiki_fired` helper |

### Key Link Verification

| From | To | Via | Status |
|------|----|----|--------|
| `cli.py distill` | `distiller.main` + `is_wiki_stale` + `_register(kind="wiki")` | load_state → staleness gate → main → register → save_state | ✓ WIRED |
| `bench/distiller.py` | `flowstate.distiller` | re-import of main + monkeypatch symbols | ✓ WIRED |
| `orchestrator.py:258` | `build_context_prefix` | `include_layers=_STANDARD_LAYERS \| {"wiki"}` when flag on else None | ✓ WIRED |
| context_prefix wiki-assembly | console one-time warning | embedder absent → warn `flowstate[semantic]` | ✓ WIRED |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Wheel-safe import | `sys.modules.pop('bench'); import flowstate.distiller` | exit 0 | ✓ PASS |
| Shim intact | `from bench.distiller import main, _WIKI_CORPUS_REL, _locate_claude` | exit 0 | ✓ PASS |
| distill CLI help | `flowstate distill --help` | lists --force/--llm/--model | ✓ PASS |
| Embedder present | `get_embedder(root).available()` | True (semantic path fires) | ✓ PASS |
| Real memory.db distillable | query 5 kinds | 0 rows (dogfood correctly skips) | ✓ PASS |
| Dogfood suite | `pytest tests/test_wiki_dogfood.py` | 1 passed, 1 skipped | ✓ PASS |
| Phase test modules | `pytest` on 7 phase modules | 208 passed, 1 skipped | ✓ PASS |
| Full suite + coverage | `pytest -q` | 1197 passed, 1 skipped, 91.28% | ✓ PASS |
| ruff | `ruff check` on 8 phase files | All checks passed | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| WIKI-03 | 21-01 | Production caller runs distiller; manifest-tracked, staleness-gated | ✓ SATISFIED | Truths 1-4; `flowstate distill` + is_wiki_stale + kind="wiki" |
| WIKI-04 | 21-02 | Opt-in flag fires wiki layer; flag off byte-identical | ✓ SATISFIED | Truth 5; byte-identity test + union constant |
| WIKI-05 | 21-02 | `flowstate[semantic]` surfaced; no-op-with-warning, never crash | ✓ SATISFIED | Truth 6; `_warn_semantic_absent` sentinel |
| WIKI-06 | 21-03 | Dogfood asserts layer fires (globbed + top-k injected), run green | ✓ SATISFIED | Truth 7 + assessment; synthetic guard fires via real semantic path |

No orphaned requirements — all four WIKI-03..06 IDs mapped to plans and REQUIREMENTS.md marks them Complete.

### Code Review Follow-up (21-REVIEW.md)

| Finding | Severity | Status | Evidence |
|---------|----------|--------|----------|
| WR-01: is_wiki_stale ignores deleted corpus | Warning | ✓ CLOSED | `distiller.py:118-125` treats absent/empty corpus dir as stale |
| WR-02: distiller never clears corpus → orphaned duplicate articles | Warning | ✓ CLOSED | `distiller.py:231-233` unlinks stale top-level `*.md` before write |
| IN-01/02/03 | Info | Non-blocking | IN-01 addressed via `__all__` in shim; IN-02 (RUN in _ARTICLE_KINDS) retained as intentional bench carry-over; IN-03 cosmetic |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| context.py | 53,90,91 | `TBD` | ℹ️ Info | Literal template-output strings ("Deliverables: TBD") emitted into generated PROJECT.md/ROADMAP.md; pre-existing, NOT in phase-modified code (phase touched only `_register` at line 38). Not a code debt marker. |

No `FIXME`/`XXX`/`HACK`/`PLACEHOLDER` in any phase-modified file. Never-raise contracts and fail-loud-on-empty preserved.

### Gaps Summary

None. All 8 must-haves verified against the actual codebase. The two Warnings from the code review (WR-01 staleness-ignores-corpus, WR-02 orphaned-articles) are both closed in `flowstate/distiller.py`. The D-03 scope fence holds (no distiller auto-invocation in run_pipeline). Byte-identity, the standard-union-not-{"wiki"}-alone wiring, single-probe degradation, and the dogfood firing guard all verify. Full suite green at 1197 passed / 1 skipped / 91.28% coverage.

The single nuance — WIKI-06's real-memory dogfood skips because this checkout's `memory.db` is genuinely empty (0 distillable rows) — is honestly documented above and judged an acceptable satisfaction: the always-green synthetic guard exercises the identical production functions through the real semantic KNN path, proving the layer fires and guarding against dormancy regression.

---

_Verified: 2026-07-11_
_Verifier: Claude (gsd-verifier)_
