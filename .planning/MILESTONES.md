# Milestones

## v0.4.0 Context Compaction & Compounding (Shipped: 2026-06-06)

**Phases completed:** 3 phases, 6 plans, 13 tasks

**Key accomplishments:**

- **Repomix pack ingredient** — `flowstate pack` shells out to the repomix CLI (located like `claude`, graceful when absent), writes `.planning/codebase/repomix-pack.xml`, manifest-tracks it, and repacks only when stale; `.mcp.json` registers repomix-MCP and `mcp__repomix` is passed to spawned agents as retrieval-on-top.
- **Karpathy canon layer** — the 4 guidelines ship as a `CANON` constant prepended to every `claude --print` system prompt (suppressible via `BridgeConfig.inject_canon`) — the most-stable CAG layer.
- **ECC-modeled eval fixtures** — `init`/`kickoff` scaffold a manifest-tracked starter fixture (retrieval_questions / acceptance_gates / forbidden_actions + system contract + exemplar) under `.planning/fixtures/`.
- **Layered CAG assembly** — `build_context_prefix()` composes fixtures → pack(if-fits) → memory once per run, threaded via the existing `prior_knowledge` seam, with a fit→compress→omit ladder (no silent truncation) and prompt-cache lean-in (`ENABLE_PROMPT_CACHING_1H` opt-in, most-stable-first ordering); canon kept out of the prefix to avoid double-injection.
- **Scaffold-only `flowstate kickoff`** — runs the (enhanced, shared) interview + context-file + pack scaffold with NO LLM pipeline; interview gained `test_coverage` range validation + `deployment_target` conditional branching, shared verbatim with `flowstate init`.
- **SUMMARY `status:` hygiene** — standardized `status:` frontmatter + backfilled the two quick tasks so `audit-open` reports zero open items.

**Quality:** 381 tests passing at 92.85% coverage; every phase passed independent goal-backward verification. Plan-checker caught a real `_migrate_state` v0.3→v0.4 guard bug and a ROADMAP success-criterion error before they shipped.

---

## v0.3.0 v2 Pivot + Operate-Safely (Shipped: 2026-06-06)

**Phases completed:** 2 phases (Phase 1 landed via direct pivot commits; Phase 2 via 4 GSD plans), 8 tasks

**Key accomplishments:**

- Landed the in-flight v2 pivot cleanly: `config.py` default-root resolution wired across the CLI, FTS5 query sanitization, built-in tool markers, version bumped to 0.3.0 (Phase 1, commit b38bbd6).
- FlowState now records every file it writes on `install_manifest`, and `flowstate fresh` consults that record instead of blind-deleting a hardcoded target list — orphans are reported, not nuked.
- `flowstate doctor` runs 6 pure-Python health checks (manifest integrity, memory schema, root, claude CLI, stale Running statuses, orphans) with exit-code = error count; `flowstate repair` applies the safe subset by default and gates orphan-deletion + corrupt-db recreation behind `--apply-destructive`, using Pydantic-immutable-safe `model_copy(update={...})` for checksum drift updates.
- `flowstate status --markdown` emits a 3-section markdown document (tools table, active phase, memory stats) for cross-session handoff; `--write` writes it to a file. Default Rich-table behavior preserved.
- Hook env-gating: `FLOWSTATE_HANDLERS=minimal|standard|strict` + `FLOWSTATE_DISABLED_HANDLERS` denylist (precedence over profile) control which event handlers register.

**Quick tasks shipped on top:** 260525-m9v (unify memory injection at orchestrator, CAG-inspired) · 260525-o6h (confirmed `claude --print` prompt cache fires: −32% wall, −37% API on call 2).

---
