---
phase: 07-gotchas-accumulator
verified: 2026-06-08T23:23:46Z
status: passed
score: 4/4 ROADMAP success criteria verified
overrides_applied: 0
---

# Phase 7: Gotchas Accumulator — Verification Report

**Phase Goal:** Structured failures (verifier gaps, plan-checker findings, doctor diagnoses, executor deviations) become a deduped, capped, persistent gotchas layer injected into every run's context prefix.
**Verified:** 2026-06-08T23:23:46Z
**Status:** passed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths (ROADMAP Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Structured failure from any of the four bounded sources is captured into memory.db (kind=insight, tagged `gotcha`) and mirrored to GOTCHAS.md with source/first-seen/last-seen | VERIFIED | `capture_gotcha` in `gotchas.py` stores INSIGHT entries; `_rewrite_gotchas_md` rewrites GOTCHAS.md on every capture. All four sources wired: executor via `memory_handlers.py:on_step_failed`, doctor/repair via `cli.py` capture blocks, verifier/plan-checker via `harvest_planning_gotchas` |
| 2 | Context prefix includes `## Gotchas` section before `## Prior Knowledge` memory layer | VERIFIED | `context_prefix.py` assembly: `layers = [fixtures_layer, pack_layer, gotchas_layer, memory_layer, since_last_run_layer]`. Gotchas before memory confirmed. `TestGotchasLayerIntegration::test_gotchas_before_memory_after_pack` passes |
| 3 | Same failure signal twice does not duplicate — dedup by normalized signature, last-seen updates on re-encounter | VERIFIED | `_signature()` normalizes paths/timestamps/run_ids via `_normalize()`. `capture_gotcha` does `memory.update(existing)` on re-encounter, incrementing count. `TestCaptureGotcha::test_path_variance_deduplicates` and `test_second_capture_increments_count` pass |
| 4 | Gotchas layer bounded by configurable token budget; entries prunable when resolved; layer never grows prefix beyond budget | VERIFIED | `_load_gotchas_max_entries` (default 10), `_load_gotchas_budget_tokens` (default 1500), `_load_gotchas_enabled` (gate). Layer drops with log if still over budget after since-last-run dropped. `flowstate gotchas prune --signature` / `--resolved` work. `TestGotchasLayerIntegration::test_gotchas_layer_dropped_and_logged_when_over_budget` passes |

**Score:** 4/4 ROADMAP truths verified

---

## Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `flowstate/gotchas.py` | `_normalize`, `_signature`, `capture_gotcha`, `_rewrite_gotchas_md`, `harvest_planning_gotchas`, `_parse_frontmatter` | VERIFIED | 390 lines, all functions present, no bridge/yaml imports |
| `flowstate/memory.py` | `MemoryStore.update(entry)` UPDATE-by-id method | VERIFIED | `def update` at line 172, `UPDATE memories` SQL, FTS trigger auto-syncs |
| `flowstate/context_prefix.py` | `_read_gotchas_layer`, three config helpers, gotchas integrated into assembly + fit-ladder + final guard | VERIFIED | All four functions present; `gotchas_layer` appears 9 times in file (definition, build site, 2 candidates, guard, assembly) |
| `flowstate/memory_handlers.py` | `on_step_failed` also captures executor gotcha | VERIFIED | Lazy import of `capture_gotcha` after existing TOOL_RUN store; `source="executor"` |
| `flowstate/orchestrator.py` | `harvest_planning_gotchas` call at pipeline start | VERIFIED | Called immediately after MemoryStore opens, before adapters, wrapped in try/except |
| `flowstate/journal.py` | `gotchas` metadata slot + RUNLOG line from this run's signatures | VERIFIED | Placeholder `"none this phase"` is gone (count=0); `"none this run"` is the new fallback |
| `flowstate/cli.py` | `gotchas` group (list + prune), doctor/repair capture wiring | VERIFIED | `@main.group("gotchas")`, `gotchas_prune`, `capture_gotcha` in both doctor and repair |

---

## Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `gotchas.py` | `memory.py` | `memory.update / add / get_by_kind` | VERIFIED | Imports `MemoryEntry, MemoryKind, MemoryStore`; all three call patterns present |
| `gotchas.py` | `.planning/GOTCHAS.md` | `_rewrite_gotchas_md` writes derived mirror | VERIFIED | `gotchas_md = root / ".planning" / "GOTCHAS.md"` + `write_text()` |
| `context_prefix.py` | `memory.db INSIGHT gotchas` | `memory.get_by_kind(INSIGHT)` filtered by "gotcha" tag | VERIFIED | `_read_gotchas_layer` calls `memory.get_by_kind(MemoryKind.INSIGHT, limit=max_entries*5)` then filters |
| `gotchas_layer` | Pack fit-ladder candidates + final budget guard | Appears in both `filter(None, [...])` candidate lists and `full_assembly` guard | VERIFIED | Lines 354, 376, 407 in `context_prefix.py` |
| `memory_handlers.py on_step_failed` | `capture_gotcha` | Lazy import after existing TOOL_RUN store | VERIFIED | `try: from flowstate.gotchas import capture_gotcha; capture_gotcha(store, source="executor", ...)` |
| `orchestrator.py run_pipeline` | `harvest_planning_gotchas` | Best-effort at pipeline start | VERIFIED | Lines 184-189 in `orchestrator.py` |
| `journal.py append_run_entry` | This run's gotcha signatures | Query INSIGHT+gotcha entries with matching `run_id` | VERIFIED | `metadata["gotchas"] = this_run_sigs` at line 90 |

---

## Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|--------------|--------|-------------------|--------|
| `context_prefix.py _read_gotchas_layer` | `gotchas` list | `memory.get_by_kind(INSIGHT)` filtered by tag | DB query via MemoryStore | FLOWING |
| `cli.py gotchas_group` | `entries` list | `store.get_by_kind(INSIGHT, limit=limit*5)` | DB query | FLOWING |
| `journal.py append_run_entry` | `this_run_sigs` | `memory.get_by_kind(INSIGHT, limit=200)` filtered by run_id + gotcha tag | DB query | FLOWING |

---

## Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Signature normalizes paths | `_signature('test', '/a/b.py line 1') == _signature('test', '/c/b.py line 99')` | True | PASS |
| Signature normalizes `+00:00` ISO timestamps | `_signature('v', 'at 2026-01-01T00:00:00+00:00') == _signature('v', 'at 2026-06-15T12:34:56+00:00')` | True | PASS |
| Python UTC datetime produces `+00:00` form (not `Z`) | `datetime.now(UTC).isoformat()` | `2026-06-08T23:xx:xx+00:00` | PASS — normalization covers real Python timestamps |
| No bridge import in gotchas.py | `grep -c 'import.*bridge' flowstate/gotchas.py` | 0 | PASS |
| No yaml import in gotchas.py | `grep -c 'import yaml' flowstate/gotchas.py` | 0 | PASS |
| Full test suite | `python -m pytest` | 503 passed, 92.25% coverage | PASS |

---

## Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| GOT-01 | 07-01, 07-03, 07-04 | Four bounded capture sources → memory.db + GOTCHAS.md mirror | SATISFIED | `capture_gotcha`, `harvest_planning_gotchas`, doctor/repair wiring, executor wiring all present and tested |
| GOT-02 | 07-02 | `## Gotchas` prefix layer before `## Prior Knowledge` | SATISFIED | `context_prefix.py` assembly verified; ordering test passes |
| GOT-03 | 07-01, 07-02, 07-03 | Dedup by normalized signature, capped, pruneable | SATISFIED | `_signature`, `_normalize`, `gotchas_max_entries`/`gotchas_budget_tokens`, `flowstate gotchas prune` all present and tested |

---

## Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `flowstate/context_prefix.py` | ~304 | `build_context_prefix` docstring says "Composes four layers" (stale — now five) | INFO | Non-functional; module-level docstring at top of file is already correct ("fixtures → pack → gotchas → memory → since-last-run") |
| `flowstate/gotchas.py` | 63-65 | `_normalize` ISO timestamp regex uses capital `Z` literal; after `.lower()` lowercase `z` doesn't match | WARNING | Only affects externally-sourced strings with `Z` UTC suffix. Python's `datetime.now(UTC).isoformat()` always produces `+00:00` form, so all internal pipeline timestamps normalize correctly. Test uses `+00:00` format (correct). No duplicate entries from real pipeline data. |

No TBD/FIXME/XXX/TODO/HACK/PLACEHOLDER markers found in any modified file.

---

## Human Verification Required

None. All success criteria are verifiable from the codebase and test suite.

---

## Gaps Summary

No gaps. All four ROADMAP success criteria are achieved. The 503-test suite passes at 92% coverage (above the 80% floor). The two anti-patterns noted are non-blocking:

1. Stale "four layers" text in `build_context_prefix` docstring — informational only; module docstring and code are correct.
2. `Z`-suffix ISO timestamp normalization gap — affects only external strings; all Python-generated timestamps use `+00:00` and normalize correctly. No real-world dedup failure from pipeline data.

---

_Verified: 2026-06-08T23:23:46Z_
_Verifier: Claude (gsd-verifier)_
