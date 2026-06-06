# Requirements: FlowState — Milestone v0.4.0 (Context Compaction & Compounding)

**Defined:** 2026-06-06
**Core Value:** Each run starts smarter than the last — durable artifacts + auto-injected memory make work compound across runs.

## v1 Requirements

Requirements for this milestone. Each maps to a roadmap phase (Phases 3–5, continuing v0.3's numbering).

### Repomix Pack (PACK)

- [ ] **PACK-01**: `flowstate pack` command shells out to the `repomix` CLI, writes a pack artifact to `.planning/codebase/repomix-pack.xml` (or `.md`), and registers it on `install_manifest` with a checksum. Locates `repomix` via PATH / `FLOWSTATE_REPOMIX_BIN` (mirroring `bridge._find_claude()`); degrades gracefully with a clear message and non-zero exit when absent.
- [ ] **PACK-02**: The pipeline repacks only when stale — the pack regenerates if any tracked source file is newer than the pack's `created_at` in the manifest; otherwise the existing pack is reused.
- [ ] **PACK-03**: repomix-MCP is registered in the project (`.mcp.json`) and exposed to spawned `claude --print` agents via `--allowed-tools` so they can grep the pack as retrieval-on-top.

### Canon (CANON)

- [ ] **CANON-01**: The four Karpathy guidelines ship as a `CANON` constant in `flowstate/bridge.py`, prepended to every `claude --print` system prompt as the first (most stable) CAG layer. Suppressible via a `BridgeConfig.inject_canon` flag (default `True`).

### Eval Fixtures (FIX)

- [ ] **FIX-01**: A fixture format modeled on ECC's `scenario.json` (`retrieval_questions`, `acceptance_gates`, `forbidden_actions`) plus a system-contract and few-shot exemplars, stored under `.planning/fixtures/` as a pack-able artifact.
- [ ] **FIX-02**: `flowstate init` / `kickoff` scaffolds a starter fixture from interview answers; the fixture is registered on `install_manifest`.

### Layered CAG Assembly (CAG)

- [ ] **CAG-01**: A single `build_context_prefix()` assembles ordered layers — canon → fixtures → pack (if it fits) → project memory — built once per run and threaded via the existing `prior_knowledge` seam into all adapters.
- [ ] **CAG-02**: Fit logic measures pack tokens; inlines the full pack when `prefix_total < budget`; else runs `repomix --compress` (~70% smaller); else omits the pack and relies on repomix-MCP retrieval-on-top. Budget is configurable and any dropped content is logged (no silent truncation).
- [ ] **CAG-03**: Layer ordering is most-stable-first to maximize cross-run cache hits; the bridge optionally sets `ENABLE_PROMPT_CACHING_1H`; cache behavior is documented on `ClaudeBridge`.

### Guided Kickoff (KICK)

- [ ] **KICK-01**: A new scaffold-only command (`flowstate kickoff`, name TBD) runs an enhanced guided interview and writes scaffold artifacts (context files, pack, starter fixture) WITHOUT invoking the LLM pipeline.
- [ ] **KICK-02**: The interview gains the kickoff questions (branching / validation) and persists them to `state.interview`; full `flowstate init` reuses the same enhanced questions.

### Developer Experience (DX)

- [ ] **DX-01**: Standardize a `status:` field (`complete` / `verified` / `blocked` / `paused` / `drafted`) in quick-task and phase SUMMARY frontmatter; backfill the two existing quick tasks so `audit-open` stops false-flagging shipped work.
- [ ] **DX-02**: Add "use the Repomix pack instead of crawling source every wave" guidance to FlowState's own `.claude/CLAUDE.md` AND the `generate_claude_md()` template for downstream projects.

## v2 Requirements

Deferred to future milestones (carried from v0.3 archive).

- **DIST-01..03**: PyPI / Flox catalog / Homebrew distribution
- **XHARN-01..03**: Codex / OpenCode / Cursor adapters
- **EVAL-01..02**: capture pipeline outputs in `runs/`; pass@k evaluator over historical runs (the *grader*, distinct from this milestone's fixture *format*)

## Out of Scope

Explicitly excluded for this milestone.

| Feature | Reason |
|---------|--------|
| Literal KV-cache / CAG preload API | No such API exists through `claude --print`; "CAG" here = prefix-cache-optimized layering against Anthropic's implicit server-side cache (confirmed in spike o6h) |
| Formal eval/grading harness with pass@k | This milestone ships the fixture *format* (rubric/contract/exemplars), not the grader — defer scoring to v2 EVAL once run history exists |
| Embeddings / vector DB on top of FTS5 | FTS5 BM25 + repomix pack + retrieval-on-top covers v0.4.0; embeddings add a dependency for marginal gain |
| New Python runtime dependencies | repomix is an external Node CLI/MCP located like `claude`; the no-new-Python-deps rule holds |
| Cross-harness packaging, Rust rewrite, GUI dashboard, declarative hooks.json | Reasons unchanged from v0.3 archive |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| PACK-01 | Phase 3 | Pending |
| PACK-02 | Phase 3 | Pending |
| PACK-03 | Phase 3 | Pending |
| CANON-01 | Phase 3 | Pending |
| FIX-01 | Phase 3 | Pending |
| FIX-02 | Phase 3 | Pending |
| DX-02 | Phase 3 | Pending |
| CAG-01 | Phase 4 | Pending |
| CAG-02 | Phase 4 | Pending |
| CAG-03 | Phase 4 | Pending |
| KICK-01 | Phase 5 | Pending |
| KICK-02 | Phase 5 | Pending |
| DX-01 | Phase 5 | Pending |

**Coverage:**
- v1 requirements: 13 total
- Mapped to phases: 13
- Unmapped: 0 ✓

---
*Requirements defined: 2026-06-06*
