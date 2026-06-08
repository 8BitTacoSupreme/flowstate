# Phase 6: Run Journal - Context

**Gathered:** 2026-06-07
**Status:** Ready for planning
**Source:** Milestone v0.5.0 plan (RUN-01/02/03) + codebase exploration (autonomous smart-discuss)

<domain>
## Phase Boundary

First phase of v0.5.0 "Compounding Loop." Goal: each pipeline run leaves an
**append-only, delta-only trail** the next run reads first. In scope: a new
`MemoryKind.RUN` journal entry written once per run (RUN-01), a `## Since Last Run`
layer appended to the CAG context prefix (RUN-02), and a `flowstate journal` read
command (RUN-03). All journal logic is **pure-Python — no LLM/bridge calls**. This
phase produces the substrate Phase 7 (Gotchas) and Phase 8 (Verification) build on;
its RUN-entry metadata carries forward-compatible empty slots for gotchas/decisions.
</domain>

<decisions>
## Implementation Decisions (LOCKED)

### RUN-01 — append one delta-only journal entry per run
- New module `flowstate/journal.py` with `append_run_entry(...)`. Pure-Python; **no
  bridge/LLM**. Called from `run_pipeline()` at the END, immediately before
  `memory.close()` (orchestrator.py ~L312).
- Add `RUN = "run"` to `MemoryKind` (memory.py L70-75). `INSIGHT` already exists; only
  `RUN` is new. This is the documented Phase-6 prerequisite from STATE.md.
- Writes **exactly one** `MemoryKind.RUN` entry per `run_id` (the orchestrator's
  `uuid4().hex[:12]`, orchestrator.py L175), stored via `memory.add()`.
- **Delta is computed pure-Python** by diffing this run against the previous
  `MemoryKind.RUN` entry's `metadata` (fetched via `memory.get_by_kind(RUN, limit=1)`
  BEFORE adding the new entry). First run (no prior RUN entry) → full snapshot, delta
  notes "first run".
- Captured fields (entry `metadata` dict + human `summary`/`content`): `run_id`,
  timestamp (`created_at`), per-step status (research/strategy/gsd/discipline — read
  from `state.tools[...].status`), **artifacts changed** (diff `state.install_manifest`
  checksums vs the prior run's recorded checksums — see Specifics), decisions (empty
  this phase), gotchas (empty this phase), and a **one-line delta** string.
- Phase-7/8 fields (`gotchas`, `decisions`) are present-but-empty in metadata so the
  schema is forward-compatible and later phases populate without a migration.

### RUN-02 — `## Since Last Run` prefix layer
- Extend `build_context_prefix()` (context_prefix.py) with a journal layer appended
  **AFTER** the memory layer (most-dynamic-last, per the ROADMAP decision). Layer order
  becomes: fixtures → pack → memory → **since-last-run**.
- Source: `memory.get_by_kind(MemoryKind.RUN, limit=N)`, newest-first, rendered as a
  `## Since Last Run` markdown section (the last N run deltas).
- `N` default **3**, configurable via a **top-level** config key
  `run_journal_prefix_entries` in `.planning/config.json`.
- **Empty journal → omit the section entirely** (no empty heading), exactly like the
  existing `if l` non-empty filter in the final assembly.
- **Must NOT import `flowstate.bridge`** (preserve the existing context_prefix
  constraint). Reads memory only.

### RUN-03 — `flowstate journal` command
- New top-level `@main.command()` `journal` in cli.py. Pure-Python read; **never raises
  on a missing/empty journal**.
- Shows the **10** most recent RUN entries by default; `--limit N` override.
- Source: `memory.db` via `MemoryStore.get_by_kind(MemoryKind.RUN, limit=...)`.
- Renders a **Rich table, newest-first**. Empty/missing journal → graceful
  `"no journal entries yet"` message, **exit 0**.
- All reads wrapped so a corrupt/absent DB degrades gracefully rather than tracebacking.

### RUNLOG.md mirror (RUN-01 cont'd)
- `memory.db` is the **canonical** store; `.planning/RUNLOG.md` is a **derived mirror**
  written by `append_run_entry` for human/git-diff visibility.
- Format: **append-only, newest-at-bottom**, one section per run:
  `## <ISO timestamp> — run <id>` followed by bullet fields (steps+status, artifacts
  changed, decisions, gotchas, one-line delta).
- **Dry-run still writes** a journal entry + RUNLOG section, tagged `dry_run` (tag on the
  MemoryEntry and noted in the RUNLOG bullet) so dry-runs are distinguishable.
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Journal core (RUN-01)
- `flowstate/memory.py` — `MemoryKind` (L70-75, add `RUN`); `MemoryEntry.create()`
  (L90-111); `MemoryStore.add()` (L152-169); `get_by_kind()` (L248-253) for prior-entry
  fetch and journal reads.
- `flowstate/orchestrator.py` — `run_pipeline()` (L163-320); call site is just before
  `memory.close()` (L312). `run_id` at L175. `state.install_manifest` checksum machinery:
  `_register_memory_artifact` (L54-69, memory.db checksum=None), `_register_tool_artifact`
  (L72-100, sha256 checksums). Per-step status lives in `state.tools[name].status`.
- `flowstate/state.py` — `InstallEntry` (path/owner/kind/created_at/checksum),
  `FlowStateModel.install_manifest`, `ToolState.status`. New module reads these; no schema
  bump required for the journal itself (entries live in memory.db, not flowstate.json).

### Prefix layer (RUN-02)
- `flowstate/context_prefix.py` — `build_context_prefix()`; `_SEPARATOR`,
  `_DEFAULT_BUDGET_TOKENS`, `_CHARS_PER_TOKEN`; final assembly
  `layers = [fixtures_layer, pack_layer, memory_layer]; non_empty = [l for l in layers if l]`.
  Append the new `since_last_run` layer to `layers`. Do NOT import `flowstate.bridge`.
- `.planning/config.json` — top-level keys (`commit_docs`, `parallelization`, ...). Add
  `run_journal_prefix_entries`. Config read pattern: check how context_prefix/cli currently
  load config.json (mirror it; likely a small json.load helper).

### Command (RUN-03)
- `flowstate/cli.py` — existing `@main.command()` patterns (init, kickoff, status, pack,
  check, doctor) and the `memory` Click group for Rich-table output conventions.

### Tests (analogs)
- `tests/test_memory.py` — MemoryKind/add/get_by_kind coverage (extend for `RUN`).
- `tests/test_context_prefix.py` — layer assembly + omission behavior (add since-last-run
  cases: empty journal omits, N respected, ordering after memory).
- `tests/test_orchestrator.py` — run_pipeline wiring (assert one RUN entry per run; assert
  append happens before memory.close).
- `tests/test_cli.py` — CliRunner; add `flowstate journal` cases (empty → exit 0 message;
  populated → table; `--limit`).
</canonical_refs>

<specifics>
## Specific Ideas

- **Artifacts-changed diff:** previous run's checksums aren't stored on the manifest
  history — store the relevant `{path: checksum}` snapshot INTO the RUN entry's `metadata`
  at write time, then the next run diffs the current `install_manifest` against the prior
  RUN entry's stored snapshot. memory.db (checksum=None) is excluded from the diff.
- **One-line delta** is the headline: e.g. `"research+strategy re-ran; roadmap.md changed;
  2 new memories"`. Keep it short — it's what `## Since Last Run` leads with.
- **Pure-Python guarantee:** `journal.py` imports only stdlib + `flowstate.memory`/`state`.
  No `bridge` import anywhere in journal.py or the context_prefix layer (mirror the existing
  context_prefix no-bridge rule).
- **Determinism for tests:** `append_run_entry` should accept the timestamp/run_id from the
  caller (orchestrator passes `run_id`); avoid hidden `datetime.now()` deep in logic where a
  test can't pin it — or expose a seam. Follow how memory.py handles `created_at`.
- **Idempotency:** one entry per run_id. If `append_run_entry` is somehow called twice for a
  run_id (re-entrancy), don't double-write — guard on existing RUN entry for that run_id.
- **Constraints:** ruff line-length 100 + double quotes, snake_case, **NO new Python runtime
  deps**, coverage ≥80% (pre-commit enforces on push). State migration must still load
  v0.1→0.2→0.3 (journal doesn't touch flowstate.json schema, so this is just "don't break
  it").
</specifics>

<deferred>
## Deferred Ideas
- Gotchas accumulation + decision capture → **Phase 7** (RUN entry metadata reserves empty
  `gotchas`/`decisions` slots now).
- Runnable verification recording → **Phase 8**.
- No raw session-transcript mining for journal/gotchas (explicit milestone constraint).
</deferred>

---

*Phase: 06-run-journal*
*Context gathered: 2026-06-07 via milestone v0.5.0 plan + codebase exploration (autonomous smart-discuss)*
