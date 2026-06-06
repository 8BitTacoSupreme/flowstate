# Milestones

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
