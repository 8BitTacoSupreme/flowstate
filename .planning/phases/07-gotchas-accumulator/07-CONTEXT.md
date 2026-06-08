# Phase 7: Gotchas Accumulator - Context

**Gathered:** 2026-06-08
**Status:** Ready for planning
**Source:** Milestone v0.5.0 plan (GOT-01/02/03) + codebase surface-map exploration (autonomous smart-discuss)

<domain>
## Phase Boundary

Second phase of v0.5.0 "Compounding Loop." Goal: structured failure signals from four
bounded sources become a **deduped, capped, persistent gotchas layer** injected into every
run's context prefix. Pure-Python, NO LLM, **NO raw session-transcript mining** — only
STRUCTURED outputs. Builds directly on the Phase 6 substrate (`build_context_prefix` layering,
`MemoryStore`, the RUN-entry `gotchas` metadata slot). In scope: GOT-01 (capture), GOT-02
(`## Gotchas` prefix layer), GOT-03 (dedup + cap + prune). Reserves nothing for later — this
is the middle phase; Phase 8 (`flowstate verify`) will FEED this accumulator (VER-02).
</domain>

<decisions>
## Implementation Decisions (LOCKED)

### GOT-01 — capture structured failure signals from all four sources
- New module `flowstate/gotchas.py`. Pure-Python (stdlib + flowstate.memory/state only; **NO
  flowstate.bridge import**). Core API: `capture_gotcha(memory, *, source, message, root, ...)`
  that normalizes → signatures → dedups/upserts → mirrors to GOTCHAS.md. Plus per-source
  harvesters.
- **Cover ALL FOUR sources** (the milestone requires it; GSD-artifact parsing is pure-Python,
  no new deps, and is the compounding-loop payoff since FlowState's own repo is a GSD project):
  1. **doctor/repair diagnoses** — capture from `Diagnosis` records (doctor.py:26-31:
     name/severity/message/fix_hint). Wire capture into the `flowstate doctor` and
     `flowstate repair` CLI commands (cli.py ~L664-712) for `severity in {error, warning}`.
  2. **executor step failures** — extend the existing `on_step_failed` handler
     (memory_handlers.py:104-118) to ALSO capture a gotcha (today it stores a `TOOL_RUN`
     entry tagged `["<tool>", "failure"]`; keep that, add a gotcha capture alongside).
  3. **verifier gaps** — pure-Python parse of `.planning/phases/*/{NN}-VERIFICATION.md`
     (YAML frontmatter `status:` + gaps/must-haves sections).
  4. **plan-checker findings** — pure-Python parse of `.planning/phases/*/{NN}-REVIEW.md`
     (BLOCKER/HIGH/MEDIUM findings).
  - Sources 3-4 are harvested ONCE at `run_pipeline` start (a `harvest_planning_gotchas(memory,
    root)` call), so prior-phase failures become durable context. Harvest is best-effort and
    never raises into the pipeline.
- **Storage:** `MemoryKind.INSIGHT` (already exists) tagged `["gotcha", "<source>"]`. Entry
  `metadata` carries: `signature`, `source`, `severity`, `first_seen` (ISO), `last_seen` (ISO),
  `count` (int). memory.db is **canonical**; `.planning/GOTCHAS.md` is the **derived mirror**
  (source / first-seen / last-seen / count per gotcha, append-or-rewrite).

### GOT-03 — dedup by normalized signature + bounded
- **Signature** = `sha256(source + "|" + normalized(message))[:16]`. `normalized()`: lowercase,
  collapse whitespace, replace absolute/relative paths → basename, replace digit runs /
  ISO timestamps / 12-hex run_ids → placeholders (`<n>`, `<ts>`, `<id>`). Pure-Python, no deps.
- **Dedup/upsert:** before insert, find an existing INSIGHT+gotcha entry whose
  `metadata.signature` matches (query via `get_by_kind(INSIGHT, ...)` filtered by tag+signature).
  - First-seen → insert new entry (count=1, first_seen=last_seen=now).
  - Re-encounter → **update** the existing entry: `last_seen=now`, `count += 1` (content/summary
    unchanged). Requires a new **`MemoryStore.update(entry)`** method (the schema already has the
    `memories_au` AFTER UPDATE FTS-sync trigger, so this fits cleanly — UPDATE by `id`).
- **Cap:** the injected set is bounded by `gotchas_max_entries` (default 10) AND a token budget
  `gotchas_budget_tokens` (default 1500). Ranking for the cap: sort by `(count desc, last_seen
  desc)`, take top-N, then trim to the token budget. `gotchas_enabled` (bool, default true) gates
  the whole feature. All three config keys read via the `_load_budget`/`_load_journal_prefix_n`
  idiom (context_prefix.py:69-104; guard `isinstance(int) and not isinstance(bool)`).

### GOT-02 — `## Gotchas` prefix layer
- New `_read_gotchas_layer(root, memory)` in context_prefix.py (mirrors the `_read_*_layer`
  convention; returns `""` when empty/disabled; **never raises**; **NO bridge import**).
- **Layer order becomes: fixtures → pack → gotchas → memory → since-last-run.** Gotchas sit
  BEFORE the memory layer (stable-ish, near fixtures) so the section benefits from the prompt
  cache.
- **Budget participation (Phase-6 CR-01 lesson — DO NOT repeat that bug):** the gotchas layer
  MUST be included in the pack fit-ladder candidate token estimates AND the final-guard drop, so
  the assembled prefix never silently exceeds `budget`. Empty/disabled → section omitted (the
  existing `[l for l in layers if l]` filter handles omission).

### Phase-6 journal wiring (closes the 6→7 link)
- Populate the empty `gotchas: []` slot in the RUN-entry metadata (journal.py:79) and the
  `- gotchas: (none this phase)` RUNLOG line (journal.py:158) with **this run's newly-captured
  gotcha signatures** (just the signatures/summaries, not full content — the delta-only ethos).

### CLI (GOT-03 surface)
- New `flowstate gotchas` command (mirrors `flowstate journal`, cli.py): lists accumulated
  gotchas most-frequent/most-recent first, `--limit N` (default 10), graceful "no gotchas
  recorded yet" on empty/missing/corrupt → **exit 0**, never raises, Rich table.
- `flowstate gotchas prune --signature <sig>` removes a specific gotcha; `flowstate gotchas
  prune --resolved` clears entries tagged `resolved`. Pruning deletes the memory.db entry and
  rewrites the GOTCHAS.md mirror.
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Gotchas core (GOT-01, GOT-03)
- `flowstate/memory.py` — `MemoryKind.INSIGHT` (L70-76); `MemoryEntry.create()` (L90-112,
  note `metadata`/`tags`); `add()` (L152-169); `get_by_kind()` (L249-254); `search()` (L207-241);
  `count()` (now supports `run_id=`). **Add `MemoryStore.update(entry)`** here (UPDATE by id; the
  `memories_au` trigger at L61-66 keeps FTS in sync).
- `flowstate/doctor.py` — `Diagnosis` (L26-31: name/severity/message/fix_hint), `run_doctor()`
  (L197-223). Source (1) capture input.
- `flowstate/repair.py` — `apply_safe_fixes()` (L34-103) returns `list[str]`. Source (1).
- `flowstate/memory_handlers.py` — `on_step_failed` (L104-118) currently stores TOOL_RUN
  tagged `["<tool>","failure"]`; extend to also capture a gotcha. Source (4).
- `flowstate/events/event.py` — `StepFailed` (L68-71), payload `{tool, error}`. Source (4).

### GSD-artifact harvest (GOT-01 sources 3-4)
- Parse `.planning/phases/*/*-VERIFICATION.md` (`status:` frontmatter + gaps) and
  `.planning/phases/*/*-REVIEW.md` (severity-classified findings). FlowState does NOT parse any
  .planning artifacts today — this is NEW pure-Python parsing (frontmatter via simple line scan;
  no yaml dep — mirror how SUMMARY frontmatter is handled elsewhere if a helper exists, else a
  minimal `--- ... ---` scanner).

### Prefix layer (GOT-02)
- `flowstate/context_prefix.py` — assembly `layers = [fixtures_layer, pack_layer, memory_layer,
  since_last_run_layer]` (L282-284); insert `gotchas_layer` BETWEEN pack and memory. Pack
  fit-ladder candidates at L220/L234-236 and the final budget guard (added in Phase 6) — the
  gotchas layer MUST join both. `_load_budget`/`_load_journal_prefix_n` idiom (L69-104) for new
  config helpers. `_read_*_layer` convention (L107/L127/L145).

### Journal wiring
- `flowstate/journal.py` — `metadata["gotchas"] = []` (L79) and RUNLOG `- gotchas:` line (L158).
  `append_run_entry` is called at orchestrator.py ~L315 before `memory.close()`.

### CLI
- `flowstate/cli.py` — `journal` command (Phase 6, ~L550) is the analog for `gotchas`
  (resolve_root + store open/close + Rich table + try/except graceful degrade). `doctor`
  (L664-712) and `repair` commands for capture wiring. `memory search --kind` Choice (~L333) —
  add `"insight"` filtering if not present.

### Tests (analogs)
- `tests/test_memory.py` — extend for `MemoryStore.update()`.
- `tests/test_gotchas.py` (NEW) — signature normalization, dedup/upsert (count + last_seen),
  per-source capture, GSD-artifact parsing, GOTCHAS.md mirror, never-raises.
- `tests/test_context_prefix.py` — gotchas layer order (before memory), budget participation,
  empty omission, no-bridge.
- `tests/test_cli.py` — `flowstate gotchas` (empty→exit 0, populated table, --limit, prune).
- `tests/test_orchestrator.py` / `tests/test_journal.py` — harvest at pipeline start; journal
  gotchas slot populated.
</canonical_refs>

<specifics>
## Specific Ideas

- **No new runtime deps:** signature via stdlib `hashlib`; GSD-artifact frontmatter via a tiny
  line scanner (do NOT add PyYAML). Confirm no yaml import sneaks in.
- **never-raises everywhere:** capture, harvest, the prefix layer, and the CLI all degrade
  gracefully — a malformed VERIFICATION.md or a SQLite hiccup must never break the pipeline or
  the command. Follow the Phase-6 `try/except Exception` contract (and ITS lesson: make
  `capture_gotcha` self-contained, not reliant on a caller's wrapper — Phase-6 WR-01).
- **Budget participation is mandatory** for the gotchas layer (Phase-6 CR-01 was exactly this
  bug for the since-last-run layer — do not reintroduce it).
- **Dedup correctness:** signature normalization must strip volatile tokens (paths, line numbers,
  timestamps, run_ids) or the same logical failure produces many "unique" gotchas. Add a test
  asserting two messages differing only by a path/line number share a signature.
- **GOTCHAS.md is a mirror, not the source of truth** — on every capture/prune, rewrite it from
  the canonical memory.db gotchas so it can't drift.
- Constraints: ruff line-length 100 + double quotes + snake_case, `from __future__ import
  annotations`, coverage ≥80% (pre-commit enforces on push), state migration v0.1→0.2→0.3
  unaffected (gotchas live in memory.db, not flowstate.json).
</specifics>

<deferred>
## Deferred Ideas
- `flowstate verify` producing gate failures that feed this accumulator → **Phase 8 (VER-02)**.
  Phase 7 must leave `capture_gotcha` callable by Phase 8 (stable signature: source + message).
- Auto-resolution of gotchas when the underlying failure stops recurring → out of scope (manual
  `prune` only this milestone).
</deferred>

---

*Phase: 07-gotchas-accumulator*
*Context gathered: 2026-06-08 via milestone v0.5.0 plan + codebase surface-map (autonomous smart-discuss)*
