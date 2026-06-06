# Phase 4: Integration — Layered CAG Assembly + Cache Lean-In - Context

**Gathered:** 2026-06-06
**Status:** Ready for planning
**Source:** Milestone v0.4.0 plan + Phase 3 outcomes + codebase exploration (auto mode)

<domain>
## Phase Boundary

Compose the Phase 3 ingredients (pack, canon, fixtures) into ONE ordered, cache-optimized
context prefix, built once per run and threaded through the existing `prior_knowledge` seam.
In scope: `build_context_prefix()` (CAG-01), fit/compress/omit logic (CAG-02), cache lean-in
(CAG-03). OUT of scope: `flowstate kickoff` + `status:` frontmatter (Phase 5).

This is the integration heart of the milestone — it wires together what Phase 3 built.
</domain>

<decisions>
## Implementation Decisions (LOCKED)

### CAG-01 — build_context_prefix()
- Single function composes ordered layers and returns one string, built ONCE per run, assigned
  to the value currently threaded as `prior_knowledge` into all adapters.
- **Layer order (most-stable-first): fixtures → pack (if it fits) → project memory.**
- **CRITICAL — do NOT include canon in this prefix.** The Karpathy canon already ships in the
  bridge SYSTEM prompt (Phase 3, `bridge.py::CANON` + `inject_canon`). `build_context_prefix()`
  builds the USER-prompt-side context that adapters prepend. Re-emitting canon here would
  double-inject it. The full CAG stack is: system-prompt canon (outermost, Phase 3) →
  [user prompt: fixtures → pack → memory → step prompt]. This phase owns the bracketed part.
- Replaces the bare `memory.get_context(_pk_query)` call in `orchestrator.py` (~L238). The memory
  layer becomes the LAST (most dynamic) section of the composed prefix.
- Each layer is clearly delimited (e.g. `## Eval Fixtures`, the pack block, `## Prior Knowledge`)
  with the existing `\n\n---\n\n` separators so prompt shape stays consistent.

### CAG-02 — Fit logic
- Measure token estimate of the assembled prefix (reuse the ~4-chars/token approximation already
  in `memory.py::get_context`).
- Decision ladder for the PACK layer specifically:
  1. `prefix_total < budget` → inline the full pack.
  2. else → re-pack with `run_pack(compress=True)` (repomix `--compress`, ~70% smaller) and retry.
  3. still over → OMIT the pack from the prefix and rely on repomix-MCP retrieval-on-top (the
     `mcp__repomix` allowed-tool wired in Phase 3 means spawned agents can still grep the pack).
- Budget is configurable (config.json knob, sensible default e.g. a fraction of context_window).
- NO silent truncation — every omit/compress decision is logged (Rich console) with what was dropped.

### CAG-03 — Cache lean-in
- Ordering most-stable-first (already the case: fixtures/pack static within a run, memory dynamic)
  maximizes Anthropic's implicit server-side prompt-cache hits across the Research → Strategy →
  GSD calls (confirmed in spike o6h; m9v made the prefix byte-identical across steps).
- Bridge optionally sets `ENABLE_PROMPT_CACHING_1H` env when spawning `claude --print`.
- Document the cache behavior + layer ordering on `ClaudeBridge` (docstring/comment).
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### The prior_knowledge seam (where the prefix attaches)
- `flowstate/orchestrator.py` — `run_pipeline()`: the `_pk_query` build + `memory.get_context()`
  call (~L220-238) and the threading of `prior_knowledge` into ResearchAdapter/StrategyAdapter/
  GSDAdapter constructors (~L246/267/290). `_make_bridge()` (~L103) sets allowed_tools (Phase 3).
- `flowstate/tools/base.py` — `ToolAdapter.__init__(..., prior_knowledge=...)` (~L33); adapters
  prepend it with `\n\n---\n\n` (research.py ~L91, strategy.py ~L95).

### Ingredient sources (Phase 3, reuse — do not rebuild)
- `flowstate/pack.py` — `run_pack(root, *, compress=False) -> PackResult`, `is_pack_stale()`, pack at
  `.planning/codebase/repomix-pack.xml`.
- `flowstate/context.py` — `generate_starter_fixture()`, fixture at `.planning/fixtures/starter.json`.
- `flowstate/bridge.py` — `CANON`, `BridgeConfig.inject_canon`, `run()` system-prompt assembly.
- `flowstate/memory.py` — `get_context(query, *, max_tokens) -> str` (the memory layer + token estimate).

### Tests (analogs)
- `tests/test_orchestrator.py`, `tests/test_orchestrator_extended.py` — pipeline wiring + prior_knowledge.
- `tests/test_memory.py` — get_context / token budget.
- `tests/test_pack.py`, `tests/test_bridge.py` — pack + canon.
- A NEW `tests/test_context_prefix.py` should cover: layer order, fit→inline, over-budget→compress,
  still-over→omit+log, byte-identical prefix across adapter calls, canon NOT duplicated in the prefix.
</canonical_refs>

<specifics>
## Specific Ideas

- Put `build_context_prefix()` either in orchestrator.py or a small new `flowstate/context_prefix.py`
  (planner's call — prefer a dedicated module if it keeps orchestrator lean and is unit-testable).
- Assert in a test that the composed prefix is byte-identical across the 3 adapter calls within a
  run (preserves the m9v cache property).
- Assert canon appears in the system prompt (bridge) but NOT in the build_context_prefix output.
- Constraints: ruff line-length 100, double quotes, snake_case, NO new Python runtime deps,
  coverage ≥80% (pre-commit enforces). repomix not on PATH (npx available); compress path tests
  must monkeypatch the fake repomix binary like Phase 3.
</specifics>

<deferred>
## Deferred Ideas
- `flowstate kickoff` + enhanced interview + `status:` SUMMARY frontmatter → Phase 5 (KICK/DX-01).
</deferred>

---

*Phase: 04-integration-layered-cag-assembly-cache-lean-in*
*Context gathered: 2026-06-06 via milestone plan + Phase 3 outcomes (auto mode)*
