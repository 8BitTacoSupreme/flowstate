# FlowState

## What This Is

FlowState is a CLI-first context orchestrator that scaffolds agentic-framework projects (GSD and friends) — it runs a deterministic 5-step pipeline (Context Generation → Research → Strategy → GSD → Discipline), wraps `claude --print` for scoped LLM calls with budget/model overrides, and persists a searchable SQLite FTS5 memory across runs.

Lives at `/Users/jhogan/frameworx`, package `flowstate`, Python 3.12+, Flox-managed env, Claude Code CLI as the LLM bridge.

## Core Value

**Each run starts smarter than the last** — the pipeline produces durable artifacts (PROJECT.md, ROADMAP.md, research/, memory.db) and auto-injects prior findings into subsequent runs, so the work compounds instead of repeating.

If everything else fails, that compounding loop is what FlowState exists to deliver.

## Current Milestone: v0.6.0 Semantic Retrieval

**Goal:** Replace lexical FTS5/BM25 retrieval with sqlite-vec semantic KNN across the memory and wiki layers, recovering the proven ~0.82 grounding accuracy (≈ oracle) that naive BM25 lost — opt-in via an optional embedder, with byte-identical fallback when absent.

**Target features:**
- New `flowstate/embeddings.py` — lazy embedding provider (`embed(texts)`, `dim`, `available()`), porting `bench/grounding.py::_default_embedder`.
- `vec0` virtual table in `memory.db` + embed-on-`add()`/`update()`; one-time lazy backfill on open (never blocks startup; degrades to FTS5 if the embedder is absent).
- Seam (a): `MemoryStore.get_context()` gains semantic KNN with FTS5/BM25 fallback.
- Seam (b): `context_prefix` wiki layer gains per-run semantic retrieval over an embedded wiki corpus.
- Optional `[semantic]` pip extra (fastembed); graceful degrade to today's lexical path when not installed.

**Key context:** Embedder is an **optional dependency with FTS5 fallback** (settled) — core install stays dep-free, semantic retrieval is opt-in. The default (no-embedder) path must stay **byte-identical** (golden `context_prefix` tests stay green). Tests must NOT require the model/network (inject fake `embed_fn`, `skipif` on `sqlite_vec`). `sqlite-vec` is already a core dep (unused); only the embedder is new (and optional). Proven by the bench arc: `wikivec` (sqlite-vec KNN over fastembed bge-small-en-v1.5, 384-dim) hit **0.825 ≈ oracle 0.800**, surfacing the correct article **17/20** at k=3 vs BM25's 3/20. Authoritative spec: `bench/SEMANTIC_RETRIEVAL_HANDOFF.md`.

## Requirements

### Validated

<!-- Shipped and confirmed valuable through prior milestones (v0.1–v0.2). -->

- ✓ 5-step pipeline orchestrator (research → strategy → gsd → discipline → context) — v0.2
- ✓ Pydantic-validated `flowstate.json` state with backward-compatible migration — v0.2
- ✓ Pluggable `ToolAdapter` pattern (research, strategy, gsd, discipline) — v0.2
- ✓ `ClaudeBridge` subprocess wrapper with `--allowed-tools`, `--max-budget-usd`, `--model`, `--effort` overrides — v0.2
- ✓ Synchronous `EventBus` with priority-ordered, error-isolated handlers — v0.2
- ✓ Persistent memory layer: SQLite + FTS5 (porter stemming, BM25 ranking) with auto-injection as `## Prior Knowledge` — v0.2
- ✓ 8-command Click CLI (`init`, `status`, `launch`, `run`, `context`, `memory`, `check`, `fresh`, `config`) — v0.2
- ✓ Interview flow + deterministic context-file generation (no LLM) — v0.2
- ✓ pytest + pytest-cov with 80% floor enforced via `--cov-fail-under=80` — v0.2
- ✓ **PIVOT-01..04**: v2 pivot landed (cli/discipline/launcher/memory/config edits + new config.py) — v0.3 / Phase 1
- ✓ **INST-01..03**: `install_manifest` on `FlowStateModel`; `init` populates with sha256; `fresh` consults manifest, reports orphans, `--force` removes them — v0.3 / Phase 2
- ✓ **DOCT-01..02**: pure-Python `flowstate doctor` (6 checks) + safe-by-default `flowstate repair` with `--apply-destructive` gate — v0.3 / Phase 2
- ✓ **STAT-01..02**: `flowstate status --markdown [--write FILE]` renders 3-section handoff doc (tools, active phase, memory stats) — v0.3 / Phase 2
- ✓ **HOOK-01..02**: `@handler(profile=...)` + `FLOWSTATE_HANDLERS` (minimal/standard/strict) + `FLOWSTATE_DISABLED_HANDLERS` precedence — v0.3 / Phase 2
- ✓ **PACK-01..03**: `flowstate pack` (repomix CLI locator + staleness repack) + `.mcp.json` + `mcp__repomix` retrieval-on-top — v0.4 / Phase 3
- ✓ **CANON-01**: Karpathy guidelines as the always-on bridge system-prompt canon layer (suppressible via `inject_canon`) — v0.4 / Phase 3
- ✓ **FIX-01..02**: ECC-modeled eval fixtures scaffolded under `.planning/fixtures/` + manifest-tracked — v0.4 / Phase 3
- ✓ **CAG-01..03**: `build_context_prefix()` (fixtures → pack-if-fits → memory) with fit→compress→omit ladder + `ENABLE_PROMPT_CACHING_1H` lean-in — v0.4 / Phase 4
- ✓ **KICK-01..02**: scaffold-only `flowstate kickoff` (no LLM) + enhanced shared interview (validation + branching) — v0.4 / Phase 5
- ✓ **DX-01..02**: `status:` SUMMARY frontmatter standardization + "use the pack" CLAUDE.md guidance — v0.4 / Phases 3+5
- ✓ **RUN-01..03**: append-only delta run journal (`MemoryKind.RUN` + `.planning/RUNLOG.md`) + `## Since Last Run` prefix layer + `flowstate journal` viewer — v0.5 / Phase 6
- ✓ **GOT-01..03**: gotchas accumulator from doctor/repair/executor + harvested VERIFICATION.md/REVIEW.md findings, `## Gotchas` prefix layer (before memory), signature dedup/cap/prune + `flowstate gotchas` — v0.5 / Phase 7
- ✓ **VER-01..02**: `flowstate verify` runs fixture gates against produced artifacts (bounded checker registry, CI-composable non-zero exit) + failures feed gotchas/journal, closing the loop — v0.5 / Phase 8

### Active

<!-- v0.6.0 Semantic Retrieval — requirements defined in REQUIREMENTS.md, mapped in ROADMAP.md. -->

- ⧗ **EMB-01..**: Optional embedding provider (`flowstate/embeddings.py`) + `[semantic]` pip extra — v0.6
- ⧗ **VEC-01..**: `vec0` vector store in `memory.db` (embed-on-add/update, lazy backfill) — v0.6
- ⧗ **MEM-01..**: Semantic KNN in `MemoryStore.get_context()` with FTS5 fallback — v0.6
- ⧗ **WIKI-01..**: Per-run semantic wiki retrieval in `context_prefix` — v0.6

### Out of Scope

<!-- Explicit boundaries with reasoning. -->

- **Declarative `hooks.json` per-project hook config** — `@handler` decorator is cleaner for now; revisit only if users need project-scoped hook definitions
- **Continuous-learning / auto "instinct" extraction from sessions** — ECC had silent-content-loss bugs here (v1.4.1 regression); leave promotion of session patterns manual until manual is the bottleneck
- **Cross-harness packaging** (Codex / OpenCode / Cursor adapters) — pulls FlowState off its `claude --print` bridge and adds 3+ install paths; defer until users ask
- **Formal eval/grading harness with pass@k metrics** — premature without enough run history to score against
- **Rust control-plane rewrite** — ECC's `ecc2/` is a 1-maintainer cautionary tale; Python is fine for FlowState's load
- **GUI dashboard** (Tkinter or Electron) — CLI + Rich is on-brand; dashboard is a maintenance sink
- **Paid tier / hosted SaaS / GitHub App** — different business model, not this project

## Context

- **v0.5.0 shipped (Compounding Loop):** run journal (`## Since Last Run`) + gotchas accumulator (`## Gotchas`, before memory) + `flowstate verify` runnable fixture gates that close the loop into both. 549 tests at 92.25% coverage. `build_context_prefix` now assembles five layers (fixtures → pack → gotchas → memory → since-last-run), all budget-participating. Pure-Python, no new runtime deps. Two new CLI commands (`flowstate journal`, `flowstate gotchas`) + `flowstate verify`. Working tree clean on `main`.
- **v0.4.0 shipped (Context Compaction & Compounding):** repomix pack + CAG layered context prefix (`build_context_prefix`) + Karpathy canon + ECC-modeled fixtures + scaffold-only `flowstate kickoff`. 381 tests at 92.85% coverage. The implicit-cache prefix (m9v/o6h spikes) is now formalized into ordered layers.
- **External tool surface grew (no Python deps):** repomix is now an expected external Node CLI/MCP (located like `claude` via PATH / `FLOWSTATE_REPOMIX_BIN`); absent → graceful degradation. `.mcp.json` registers repomix-MCP for spawned-agent retrieval-on-top.
- **v2 pivot landed (v0.3.0):** `config.py` default-root resolution, FTS5 sanitization, built-in tool markers (Phase 1, b38bbd6).
- **ECC comparison done:** Researched `affaan-m/ECC`. Borrowed install-manifest/doctor/hook-profiles (v0.3) and the eval-fixture format (v0.4); explicitly rejected the surface-area-explosion patterns (Out of Scope).
- **Single maintainer.** Granularity favors "few broad phases" — v0.4.0 ran 3 coarse phases (ingredients → integration → UX).

## Constraints

- **Tech stack:** Python 3.12+, Click for CLI, Pydantic for state, SQLite + FTS5 for memory, subprocess for the Claude bridge. No new **core** runtime dependencies; v0.6.0 adds the embedder strictly as an **optional `[semantic]` extra** with a lexical FTS5/BM25 fallback, so the default install stays dep-free.
- **Coverage:** ≥80% enforced by `pyproject.toml` (`--cov-fail-under=80`). Pre-commit runs ruff (legacy + format), trailing-whitespace, EOF, large-file, merge-conflict, debug-statement checks.
- **Bridge:** Claude Code CLI v2+ must be locatable; FlowState invokes `claude --print` non-interactively. No direct Anthropic API calls.
- **Compatibility:** State migration must work from v0.1.0 → v0.2.0 → v0.3.0 → v0.4.0 → v0.5.0 → v0.6.0 (each milestone bumps minor; `_migrate_state` ladder + early-exit guard kept in sync). v0.5 added journal/gotchas to `memory.db` only. v0.6 adds a `vec0` table to `memory.db` additively (one-time lazy backfill on open, never blocking) — existing `memory.db` files and the `flowstate.json` schema stay valid; no embedder → degrade to FTS5.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Coarse granularity (2 phases) | Single maintainer, scope is bounded, "one small phase" was the explicit user framing for the operate-safely work | ✓ Validated (v0.3) — both phases shipped clean |
| Land v2 pivot before adding new surface | Compounding the unstaged work with new features makes the diff unreviewable and the bug surface ambiguous | ✓ Validated (Phase 1, b38bbd6) |
| Skip Codex/OpenCode/Cursor adapters | ECC ships to 7 harnesses with one maintainer and it's visibly straining; FlowState stays Claude-Code-native until users ask | — Pending |
| Hook profile via env var, not config file | Matches ECC's pattern (`ECC_HOOK_PROFILE`) and avoids a new config surface; one env var + one filter pass at handler register time | ✓ Validated (HOOK-01/02) |
| Borrow install-manifest pattern from ECC | `flowstate fresh` is currently destructive without a manifest of what it owns — same gap ECC's `doctor`/`repair` exists to solve | ✓ Validated (INST-01..03, DOCT-01..02) |
| "CAG" = prefix-cache-optimized layering, not literal KV preload | No KV-preload API exists through `claude --print`; lean on Anthropic's implicit server-side cache with a stable, most-stable-first prefix (proven by o6h spike) | ✓ Validated (CAG-01..03, v0.4) |
| Canon in the bridge system prompt, NOT in `build_context_prefix` | The user-prompt prefix and system-prompt canon are separate channels; re-emitting canon in the prefix would double-inject it every call | ✓ Validated (Phase 4 — plan-checker caught the ROADMAP SC wording before it shipped) |
| repomix as external CLI/MCP, not a Python dependency | Keeps the no-new-runtime-deps rule; located like `claude`, degrades gracefully when absent | ✓ Validated (PACK-01..03, v0.4) |
| Decouple `flowstate kickoff` from the LLM pipeline | A fast scaffold-and-stop entry point is distinct from full `init`; both share one `run_interview` to avoid divergence | ✓ Validated (KICK-01/02, v0.4) |
| Journal/gotchas/verify are pure-Python, no LLM, no transcript mining | The compounding loop must be deterministic, cheap, and inspectable; bounded to STRUCTURED outputs to avoid the ECC silent-content-loss regression | ✓ Validated (v0.5 — zero bridge imports across journal/gotchas/verify) |
| Gotchas layer placed BEFORE memory, since-last-run AFTER | Gotchas are stable-ish (cache near fixtures); the run delta is the most dynamic slot — most-stable-first ordering preserves the prompt cache | ✓ Validated (GOT-02/RUN-02, v0.5) |
| All prefix layers must participate in the budget fit-ladder + final guard | A new layer appended without budget accounting silently blows the cache window (caught as CR-01 in Phase-6 review; reapplied to the gotchas layer) | ✓ Validated (v0.5 — review-enforced) |
| `flowstate verify` SKIPs un-checkable NL gates, never fabricates verdicts | Pure-Python can't evaluate "all functionality works"; honesty (real checks for the checkable subset, explicit SKIP otherwise) beats theater | ✓ Validated (VER-01, v0.5) |
| Skip Codex/OpenCode/Cursor adapters | ECC ships to 7 harnesses with one maintainer and it's visibly straining; FlowState stays Claude-Code-native until users ask | — Pending (still deferred at v0.4) |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd:transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-06-18 — v0.6.0 Semantic Retrieval milestone started*
