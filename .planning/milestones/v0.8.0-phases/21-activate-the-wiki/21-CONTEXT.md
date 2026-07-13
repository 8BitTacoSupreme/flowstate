# Phase 21: Activate the Wiki - Context

**Gathered:** 2026-07-11
**Status:** Ready for planning
**Source:** discuss-phase `--auto` (all gray areas auto-resolved to recommended options; single pass)

<domain>
## Phase Boundary

Wire the already-built memory→wiki distiller (`bench/distiller.py`) and the dormant Phase-11 semantic wiki layer (`flowstate/context_prefix.py`) into **production**, so the proven-best context layer (distilled wiki + semantic retrieval, measured 0.825 ≈ oracle 0.800) actually fires on production runs — **with the default path staying byte-identical when the flag is off.** WIKI-03..06.

**In scope:** promote the distiller to a production module + an explicit `flowstate distill` command (manifest-tracked, staleness-gated); an opt-in config flag that makes the orchestrator include the wiki layer; graceful `[semantic]`-absent degradation with a warning; a dogfood smoke-test proving the layer fires.

**Out of scope (scope fence — do NOT build):**
- **Auto-distilling at the end of every `run_pipeline`** — explicitly deferred (ROADMAP "Deferred Ideas": WIKI-03 ships *explicit-first*; auto-once-proven is a follow-up once the Phase-22 verdict justifies the invisible loop). Ship the explicit command only.
- **Curated/hand-authored wiki articles** — the corpus is *generated* by the distiller from `memory.db`; hand-authoring bypasses the compounding architecture.
- **New core runtime deps** — the semantic path stays behind the optional `[semantic]` extra; default install stays dep-free.
- **Measuring quality improvement** — that's Phase 22 (The Verdict). Phase 21 acceptance is "the layer demonstrably fires," NOT "quality improved."

</domain>

<decisions>
## Implementation Decisions

### Distiller promotion (WIKI-03)
- **D-01:** Promote `bench/distiller.py` to a **production module `flowstate/distiller.py`**. `bench/` re-imports from `flowstate` (bench already imports `flowstate.memory`), so the bench arm keeps working with no logic duplication. Preserve the module's **never-raise** contract and its **fail-loud-on-empty-memory** behavior.
- **D-02:** Add an **explicit `flowstate distill` CLI command** (the production entry point per SC#1). It reads this project's `memory.db`, writes the `.planning/codebase/wiki/` article corpus, and is the thing a user/pipeline runs "end-of-run." Keep the distiller's existing `--force` / `--densify` semantics.

### Distill trigger & staleness (WIKI-03)
- **D-03:** **Do NOT auto-invoke the distiller inside `run_pipeline`.** "End-of-run so the next run reads this run's distilled knowledge" is satisfied by the explicit command + staleness gate: you distill after a run, and the next run's wiki layer reads the fresh corpus. Auto-invocation is the deferred idea — leave `run_pipeline` unchanged on the distill side.
- **D-04:** **Staleness mirrors `flowstate/pack.py`.** Register the wiki corpus on `install_manifest` with `kind="wiki"` (like pack's `kind="pack"`). Staleness = `memory.db` mtime is newer than the manifest entry's `created_at` — regenerate **only when memory changed** (unless `--force`). `flowstate distill` skips work and reports "corpus up to date" when not stale. Add an `is_wiki_stale(root, state)` helper paralleling `is_pack_stale`.

### Opt-in production wiring (WIKI-04)
- **D-05:** Add an **opt-in config flag** (bool, default **false**), e.g. `wiki_layer` in `config.json` / `ProjectPreferences`, resolved the same way as other prefs. Default false ⇒ the orchestrator passes `include_layers=None` ⇒ **byte-identical to today's output** (hard requirement, SC#2).
- **D-06 (critical wiring subtlety):** When the flag is **on**, the orchestrator must pass `include_layers = frozenset({"fixtures", "pack", "gotchas", "memory", "since_last_run", "wiki"})` — the **full standard set UNION `{"wiki"}`**, NOT just `{"wiki"}`. Because `_included(key)` returns `include_layers is None or key in include_layers`, passing `{"wiki"}` alone would set every standard layer to `False` and silently drop fixtures/pack/gotchas/memory/since_last_run. The wiring adds wiki to the existing layers; it does not replace them. (Consider a small helper/constant `_STANDARD_LAYERS` so the union is defined in one place and can't drift.)

### `[semantic]`-absent degradation (WIKI-05)
- **D-07:** With the flag **on** but the `[semantic]` extra / embedder **absent**, the wiki layer is a **no-op-with-warning, never a hard crash.** The layer already degrades (`_semantic_wiki_layer` → `None` without an embedder → static `_read_wiki_layer` → empty string when no corpus). Add a **one-time console warning** at the wiki-assembly point that names the requirement: `pip install flowstate[semantic]`. Run continues green with the wiki layer contributing empty content.

### Dogfood smoke-test (WIKI-06)
- **D-08:** A **dogfood integration test** that: (1) ensures a wiki corpus exists by running the distiller against **this project's real `memory.db`**, (2) calls `build_context_prefix(..., include_layers={standard ∪ "wiki"})`, and (3) asserts the wiki layer **demonstrably fires** — the corpus is globbed and top-k article content appears in the assembled prefix, with the run green. **Acceptance = "the layer fires," NOT "quality improved."** Degrade gracefully: if `[semantic]` is absent, assert firing via whichever path is available (static `_read_wiki_layer`); if neither semantic nor any corpus can be produced, `skip` with an explicit reason rather than fail. Mark it slow/integration if it makes a real `claude`/embedder call.

### Claude's Discretion
- Exact config-key name (`wiki_layer` vs `enable_wiki_layer`), the `flowstate distill` flag surface beyond `--force`/`--densify`, the manifest `kind` string, the precise warning wording, and whether `_STANDARD_LAYERS` is a module constant or inlined — planner/executor discretion, provided the decisions above hold (especially D-03 fence, D-06 union, D-05 byte-identity).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### The producer to promote (WIKI-03)
- `bench/distiller.py` (190 LOC) — `main(argv)` with `--root`/`--force`/`--densify`; reads `memory.db` via `flowstate.memory.MemoryStore`, renders one article per `MemoryKind`, writes `.planning/codebase/wiki/`, never raises, fails loud on empty memory. This is what moves to `flowstate/distiller.py` (D-01).

### The staleness/manifest pattern to mirror (WIKI-03)
- `flowstate/pack.py` — `run_pack()` registers the artifact on `install_manifest` with `kind="pack"` (line ~141); `is_pack_stale(root, state)` compares newest source mtime vs the manifest entry's `created_at.timestamp()` (lines 152-173). Mirror this exactly for `kind="wiki"` with `memory.db` as the staleness source (D-04).

### The dormant consumer to activate (WIKI-04/05)
- `flowstate/context_prefix.py` — `build_context_prefix(root, memory, query, *, include_layers=None, ...)` (line 442). Wiki is opt-in: `wiki_included = include_layers is not None and "wiki" in include_layers` (line 509); on inclusion it tries `_semantic_wiki_layer` (KNN over `.planning/codebase/wiki/`, line 224) then falls back to `_read_wiki_layer` (static `.planning/codebase/wiki.md`, line 419). `_included(key)` = `include_layers is None or key in include_layers` (line ~496) — **the reason D-06's union matters.** `_load_wiki_k` (line 193) / `_DEFAULT_WIKI_K=3` (line 66).
- `flowstate/orchestrator.py:254` — `build_context_prefix(root, memory, _pk_query, console=console)`, currently NO `include_layers` ⇒ wiki never fires. **This is the exact call site WIKI-04 changes** (pass the union when the flag is on).

### Config + memory
- `flowstate/config.py` / `ProjectPreferences` in `flowstate/state.py` — where the opt-in flag (D-05) is resolved.
- `flowstate/memory.py` — `MemoryStore`, `MemoryKind`; `memory.db` is the distiller's source and the staleness signal.

### Phase spec
- `.planning/ROADMAP.md` §"Phase 21: Activate the Wiki" — goal + 4 success criteria + the **Deferred Ideas** fence (explicit-first, D-03).
- `.planning/REQUIREMENTS.md` — WIKI-03, WIKI-04, WIKI-05, WIKI-06.
- `.planning/PROJECT.md` — WIKI context; the memory note that this layer measured 0.825 ≈ oracle 0.800 but ships dormant (WIKI-F1) is exactly what this phase discharges.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `bench/distiller.py` — the whole producer; promote as-is to `flowstate/distiller.py`.
- `flowstate/pack.py::run_pack` / `is_pack_stale` — the manifest-register + staleness template to clone for wiki.
- `context_prefix.py` wiki machinery (`_semantic_wiki_layer`, `_read_wiki_layer`, `_load_wiki_k`) — already built (Phase 11); this phase only turns it on and hardens degradation.
- `install_manifest` on `FlowStateModel` (kind-tagged entries) — reuse for `kind="wiki"`.

### Established Patterns
- **Opt-in layer, byte-identical default** — the entire design contract; `include_layers=None` is the default path and must not change (D-05).
- **`_included` union semantics** — passing an explicit set REPLACES the default-all behavior, so wiki-on must re-list the standard layers (D-06).
- **Never-raise / graceful-degrade** — distiller never raises; the wiki layer degrades to empty without an embedder. WIKI-05 adds the warning, not a crash path.
- **Optional `[semantic]` extra** — fastembed stays optional; core install dep-free.

### Integration Points
- New `flowstate distill` CLI command (production entry point).
- New `is_wiki_stale` + `kind="wiki"` manifest registration.
- One changed call site: `orchestrator.py:254` passes the layer union when the flag is on.
- One-time `[semantic]`-absent warning at the wiki-assembly point.
- Dogfood test against the project's real `memory.db`.

</code_context>

<specifics>
## Specific Ideas

- The staleness gate is what makes "end-of-run" true *without* auto-invocation: distill writes the corpus; the next run's wiki layer reads it. That's the deferred-safe interpretation of SC#1.
- D-06 is the single most likely bug: `include_layers={"wiki"}` alone would nuke the other four layers. Lock the union.

</specifics>

<deferred>
## Deferred Ideas

- **Auto-distill at the end of every `run_pipeline`** — deferred to a post-verdict follow-up (ROADMAP fence). Phase 21 ships the explicit `flowstate distill` command only (D-03).

</deferred>

---

*Phase: 21-activate-the-wiki*
*Context gathered: 2026-07-11 via discuss-phase --auto*
