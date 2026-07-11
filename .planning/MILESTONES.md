# Milestones

## v0.6.1 Make the Names Real (Shipped: 2026-07-11)

**Phases completed:** 4 phases (12–15), 15 plans

**Key accomplishments:**

- **Honesty & failure-capability (Phase 12, HON-01..06)** — a broken run can no longer report "completed." `discipline.check_setup()` derives `success` from a required-set instead of a hardcoded `True`; the orchestrator reads the audit and marks the step `BLOCKED`; research/strategy return `success=False` on failure instead of writing stub text as artifacts; a live run with no locatable `claude` CLI fails loud rather than persisting `[dry-run]` text.
- **Adapters earn their names (Phase 13, MECH-01..03)** — each adapter now performs its namesake mechanism in pure Python + `claude --print`: research scores each section for groundedness against the fixture's `retrieval_questions` and retries-or-discards (Autoresearch measure→keep/discard over *output*); strategy emits a parseable scored rubric (five 0–10 dims + ship/pivot/kill verdict, unparseable → fail via HON-04); discipline runs the project's tests + reads real git state + checks hook contents, with `tests_pass` a **gating** required-set member and `--dry-run` zero-spawn.
- **Vendor & surface (Phase 14, VEND-01..05)** — vendored the two MIT skill sets (gstack 59 + superpowers 14 SKILL.md trees, pinned SHAs, dual attribution); `flowstate install-skills` (auto-invoked by init/kickoff) installs them zero-manual; `flowstate launch strategy` → gstack `/office-hours`, `launch discipline` → superpowers TDD, gated on install. README reconciled to shipped reality.
- **Bundle GSD (Phase 15, GSD-01..05)** — reversed "no cross-harness packaging": vendored a **51 MB lean full-parity** GSD (`get-shit-done-cc@1.42.3`, `--omit=optional` drops the redundant 197 MB platform `claude` binary; `gsd-sdk` needs its `node_modules`, a raw git clone ships a broken CLI). `install-skills` lays GSD down unconditionally (no detect, no prompt); `launch gsd` is unconditional; `flowstate gsd-version` gives a pinned-only refresh path. E2E-verified: `gsd-sdk query` runs "Bundle GSD" from a fresh project, zero separate install.

**Quality:** 1045 tests passing at ~91% coverage. No new Python runtime deps; core install stays dependency-free; vendored assets are data (excluded from coverage/collection, force-included in the wheel). Every phase passed independent goal-backward verification + a live E2E smoke.

## v0.6.0 Semantic Retrieval (Shipped: 2026-07-10)

**Phases completed:** 3 phases, 4 plans, 4 tasks

**Key accomplishments:**

- **Embedding provider (Phase 9, 09-01)** — `flowstate/embeddings.py` adds `get_embedder()`/`Embedder` behind an optional `[semantic]` extra (`fastembed>=0.3`). fastembed is imported lazily inside `_ensure_model()`, never at module top-level, so `import flowstate.embeddings` succeeds without it. Model-name precedence (`FLOWSTATE_EMBED_MODEL` env > `.planning/config.json` > `BAAI/bge-small-en-v1.5`) mirrors `context_prefix._load_budget`. Injected `embed_fn` keeps all 20 tests fully offline.
- **Vector store (Phase 9, 09-02)** — `MemoryStore` gained a `memories_vec` sqlite-vec `vec0` table with embed-on-write, delete-then-insert upsert, and an idempotent never-raises lazy backfill on open. `enable_load_extension(False)` immediately after `sqlite_vec.load()` re-scopes the extension-load surface (T-09-03). Dim is derived from `embedder.dim` at open time.
- **Semantic memory retrieval (Phase 10, MEM-01/02)** — `MemoryStore.get_context()` now serves semantic KNN when vectors exist and falls back to a byte-identical FTS5/BM25 path when they don't. Relevance is gated by an L2 distance threshold (`_SEMANTIC_MAX_DISTANCE = 0.89`, ≈ cosine 0.60), **not** by an FTS5 pre-gate — a Critical code-review catch, since a lexical gate would have suppressed exactly the lexically-disjoint-but-semantically-relevant case the milestone exists to serve.
- **Semantic wiki retrieval (Phase 11)** — ephemeral in-memory `vec0` KNN over a wiki article corpus feeds per-run top-k articles into the opt-in `context_prefix` wiki layer, with a byte-identical default (no `include_layers`) path and a never-raises static fallback.

**Quality:** 749 tests passing at 92.19% coverage. Core install stays dependency-free; every semantic path degrades silently to FTS5 when `[semantic]` is absent, and all default code paths are byte-identical to v0.5.0.

**Known deferred items at close:** 1

- **WIKI-F1** — no production caller passes `include_layers={"wiki"}` yet. The wiki retrieval mechanism is implemented and tested, but firing it needs a curated `.planning/codebase/wiki/` corpus plus orchestrator wiring. Carried into the backlog.

**Errata:** `10-01-SUMMARY.md` frontmatter records a decision ("FTS5 relevance gate added inside `_semantic_results`") that the shipped code contradicts — `_semantic_results` uses the distance threshold and its docstring explicitly rejects an FTS5 gate. The summary frontmatter drifted from the final post-review implementation; the code is authoritative.

---

## v0.5.0 Compounding Loop (Shipped: 2026-06-09)

**Phases completed:** 3 phases, 10 plans, 18 tasks

**Key accomplishments:**

- **Run journal (Phase 6, RUN-01..03)** — `journal.append_run_entry` writes one append-only, delta-only `MemoryKind.RUN` entry per pipeline run (pure-Python, idempotent, checksum-snapshot diff vs prior run) mirrored to `.planning/RUNLOG.md`; surfaced as a `## Since Last Run` prefix layer (most-dynamic slot, budget-participating) and inspectable via `flowstate journal`.
- **Gotchas accumulator (Phase 7, GOT-01..03)** — `gotchas.py` promotes structured failures from all four bounded sources (doctor/repair diagnoses, executor step failures, and harvested GSD VERIFICATION.md/REVIEW.md findings) into a deduped (normalized sha256 signature, last-seen/count upsert via new `MemoryStore.update`), capped `## Gotchas` prefix layer placed before memory; `flowstate gotchas` list/prune CLI + `.planning/GOTCHAS.md` mirror. No raw transcript mining.
- **Runnable verification (Phase 8, VER-01..02)** — `flowstate verify` turns fixture `acceptance_gates`/`forbidden_actions` into a bounded checker registry (produced-artifact integrity backbone + coverage-threshold gate, honest SKIP for un-checkable NL gates), CI-composable non-zero exit, never-raises; failures close the loop by feeding the gotchas accumulator and appending an `append_verify_entry` run-journal entry the next run reads first.

**Quality:** 549 tests passing at 92.25% coverage; every phase passed independent goal-backward verification and an adversarial code-review→fix pass (caught + fixed a CR-01 budget-participation gap, a CR-02 dedup-source mislabel, a Z-suffix-timestamp dedup miss, and a 500-entry dedup-scan scaling bug before close). No new runtime dependencies; pure-Python journal/gotchas/verify with zero `flowstate.bridge` imports.

---

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
