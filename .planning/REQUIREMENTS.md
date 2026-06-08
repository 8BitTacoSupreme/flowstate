# Requirements: FlowState — Milestone v0.5.0 (Compounding Loop)

**Defined:** 2026-06-07
**Core Value:** Each run starts smarter than the last — durable artifacts + auto-injected memory make work compound across runs.

## v1 Requirements

Requirements for this milestone. Each maps to a roadmap phase (Phases 6–8, continuing v0.4's numbering). Builds on the v0.4 `build_context_prefix()` CAG layering (`flowstate/context_prefix.py`) and the existing `MemoryStore` (`flowstate/memory.py`).

### Run Journal (RUN)

- [x] **RUN-01**: Each pipeline run appends ONE delta-only entry to an append-only run journal — persisted as a memory entry (`MemoryKind.RUN`, new kind) AND mirrored to `.planning/RUNLOG.md`. The entry captures `run_id`, timestamp, steps executed + status, artifacts changed, decisions emitted, gotchas encountered, and a one-line "since last run" delta. Entry generation is pure-Python (no LLM).
- [x] **RUN-02**: `build_context_prefix()` gains a `## Since Last Run` layer sourced from the last N run-journal entries, appended AFTER the memory layer (most-dynamic slot) so the canon → fixtures → pack → memory prefix stays cache-stable. N is configurable; absent journal → layer omitted.
- [x] **RUN-03**: `flowstate journal` command lists recent run entries (newest first, bounded/configurable) for handoff/inspection; pure-Python, never raises on a missing journal.

### Gotchas Accumulator (GOT)

- [x] **GOT-01**: Structured failure signals — verifier gaps (VERIFICATION.md), plan-checker findings, `doctor`/`repair` diagnoses, and executor deviations — are captured into a persistent gotchas store (`MemoryKind.INSIGHT` tagged `gotcha`, mirrored to `.planning/GOTCHAS.md`) with source, first-seen, last-seen. Bounded to these structured outputs — NO raw session-transcript mining.
- [ ] **GOT-02**: `build_context_prefix()` gains a `## Gotchas` layer injecting the accumulated gotchas, placed before the memory layer (stable-ish, near fixtures) so it benefits from the prompt cache.
- [x] **GOT-03**: Gotchas are deduped (by normalized signature) and capped (most-recent / most-frequent N, configurable token budget) so the layer never grows unbounded; resolved/superseded gotchas can be pruned.

### Runnable Verification (VER)

- [ ] **VER-01**: A `flowstate verify` command turns eval-fixture `acceptance_gates` / `forbidden_actions` (`.planning/fixtures/`) into runnable checks against produced artifacts — human-readable report, non-zero exit on failure so it composes in CI/pre-commit like `flowstate doctor`. Pure-Python; no LLM.
- [ ] **VER-02**: `flowstate verify` failures auto-feed the gotchas accumulator (GOT-01) and append a run-journal entry (RUN-01), closing the loop: a failed gate becomes durable context the next run sees.

## v2 Requirements

Deferred to future milestones (carried forward).

- **DIST-01..03**: PyPI / Flox catalog / Homebrew distribution
- **XHARN-01..03**: Codex / OpenCode / Cursor adapters
- **EVAL-01..02**: capture pipeline outputs in `runs/`; pass@k / pass^k scoring over historical runs (the *grader*; v0.5 makes verification *runnable* but does not score statistically)

## Out of Scope

Explicitly excluded for this milestone.

| Feature | Reason |
|---------|--------|
| Full pass@k / pass^k eval-grading harness | v0.5 makes fixtures *runnable* (pass/fail per gate) and closes the failure→context loop; statistical scoring over run history stays EVAL/v2 (needs run corpus first) |
| Auto-mining raw session transcripts for gotchas | The ECC v1.4.1 silent-content-loss footgun; gotchas are bounded to STRUCTURED verifier/checker/doctor/executor outputs, never free-form transcript scraping |
| LLM-authored journal/gotchas entries | Journal + gotchas are deterministic pure-Python derivations of run state — no bridge call, keeps them cheap, reproducible, and cache-neutral |
| Embeddings / vector ranking for gotchas relevance | FTS5 + recency/frequency cap is sufficient at current scale; embeddings add a dependency for marginal gain |
| New Python runtime dependencies | Journal, gotchas, and verify are stdlib + existing rich/pydantic/sqlite; repomix stays the only external (Node) tool |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| RUN-01 | Phase 6 | Complete |
| RUN-02 | Phase 6 | Complete |
| RUN-03 | Phase 6 | Complete |
| GOT-01 | Phase 7 | Complete |
| GOT-02 | Phase 7 | Pending |
| GOT-03 | Phase 7 | Complete |
| VER-01 | Phase 8 | Pending |
| VER-02 | Phase 8 | Pending |

**Coverage:**
- v1 requirements: 8 total
- Mapped to phases: 8
- Unmapped: 0 ✓

---
*Requirements defined: 2026-06-07*
