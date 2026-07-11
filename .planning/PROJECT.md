# FlowState

## What This Is

FlowState is a CLI-first context orchestrator that scaffolds agentic-framework projects (GSD and friends) — it runs a deterministic 5-step pipeline (Context Generation → Research → Strategy → GSD → Discipline), wraps `claude --print` for scoped LLM calls with budget/model overrides, and persists a searchable SQLite FTS5 memory across runs.

Lives at `/Users/jhogan/frameworx`, package `flowstate`, Python 3.12+, Flox-managed env, Claude Code CLI as the LLM bridge.

## Core Value

**Each run starts smarter than the last** — the pipeline produces durable artifacts (PROJECT.md, ROADMAP.md, research/, memory.db) and auto-injects prior findings into subsequent runs, so the work compounds instead of repeating.

If everything else fails, that compounding loop is what FlowState exists to deliver.

## Current State: v0.6.2 Make the Harness Real — SHIPPED 2026-07-11 (Phases 16–18)

**Shipped 2026-07-11.** The eval harness itself now runs end-to-end and **fails loud** — the measurement apparatus is honest before any further benchmarking. Phase 16 made reporting mode-honest (real mode never leaks the cheap-mode caveat; every report states mode/arm/sample-size/producers — HAR-01); Phase 17 killed silent no-op arms (absent producer → "arm measured nothing" + exit 3) and shipped the memory→wiki distiller writing the article corpus the Phase-11 reader globs, behind one `prepare-fixture` path (HAR-02/03); Phase 18 wired a seeded paired-bootstrap CI and the one-command prior-runs→distill→inject→judge→CI loop (`bench/close_loop.py`) plus a CI-safe E2E smoke over every arm (HAR-04/05). ~1110 tests at ~90% coverage; every phase passed goal-backward verification, and a post-review pass fixed a **critical paired-statistics mispairing** (dropped trials desynchronized arm vs. baseline) and a silently-swallowed judge-contract break before close. Archive: [`milestones/v0.6.2-ROADMAP.md`](./milestones/v0.6.2-ROADMAP.md).

**Prior — v0.6.1 Make the Names Real (Phases 12–15, shipped 2026-07-11):** Made the pipeline honest and the adapters real, then bundled the upstream tools self-contained. Phase 12 gave failure representability (discipline can fail, orchestrator reads the audit, research/strategy surface failure, live-no-`claude` fails loud — HON-01..06); Phase 13 gave each adapter its namesake mechanism (research groundedness measure→keep/discard, strategy scored rubric + ship/pivot/kill verdict, discipline runs tests + real git state + hook contents with `tests_pass` gating — MECH-01..03); Phase 14 vendored the gstack (59) + superpowers (14) MIT skills with `flowstate install-skills` + `launch` surfacing (VEND-01..05); Phase 15 bundled a **51 MB lean full-parity GSD** (`get-shit-done-cc@1.42.3`, `--omit=optional` drops the redundant 197 MB platform `claude` binary) that installs unconditionally and runs `gsd-sdk` zero-install (GSD-01..05). 1045 tests at ~91% coverage; every phase passed independent goal-backward verification + a live E2E smoke. Archive: [`milestones/v0.6.1-ROADMAP.md`](./milestones/v0.6.1-ROADMAP.md). (Prior: [v0.6.0 Semantic Retrieval](./milestones/v0.6.0-ROADMAP.md), shipped 2026-06-18.)

## Current Milestone: v0.8.0 Harness Tax & Value (next — phases 19–22)

**Goal:** Now that the harness is trustworthy (v0.6.2), answer the question v0.7.0 deliberately doesn't: **does FlowState's context stack improve output quality enough to justify its token and latency cost?** Four phases (SEED-001): **19 — The Tax** (real token/cost/latency accounting; `BridgeResult.usage`), **20 — Evaluator independence** (fail loud when judge-model = producer-model; multi-judge averaging), **21 — Activate the wiki** (the dormant WIKI-F1 layer — promote the memory→wiki distiller into production, add the opt-in reader caller behind a config flag with a byte-identical default, dogfood smoke-test on FlowState as phase acceptance), **22 — The verdict** (pre-registered paired-design run via `bench/close_loop.py` on a real repo, measuring the compounding curve, quality **and** tax per arm; a null `wiki − none` is an accepted outcome). The bench-side halves shipped in v0.6.2; this milestone is the production + measurement science half. Full scope: [`seeds/SEED-001-harness-tax-and-value.md`](./seeds/SEED-001-harness-tax-and-value.md).

<details><summary>📋 Deferred: v0.7.0 Retrieval Benchmark Rigor (resumes after v0.6.1; renumbers to phases 16-21)</summary>

**Goal:** Convert FlowState's "just ahead of BM25" retrieval result into a defensible, statistically significant, production-viable win — or honestly conclude it isn't there. Discharges v0.6.0's deferred reranking/fusion decision. Full 18-requirement spec preserved at `.planning/deferred/v0.7.0-REQUIREMENTS.md`.

Headline insight (verified): `recall_any@5` is **0.966 for both** BM25 and chunked-semantic while `recall_all@5` is 0.866 / 0.844 — a **ranking** problem. A perfect reranker over a top-R pool scores exactly `recall_all@R` (dense→rerank@10 caps 0.946, BM25→rerank@10 caps 0.904). The lead is untestable until per-instance dumps land; LongMemEval-S is type-blocked so `--limit` is biased. Deferred behind v0.6.1 because benchmarking an enforcement layer that cannot fail measures nothing.

</details>

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
- ✓ **EMB-01..04**: optional embedding provider (`flowstate/embeddings.py`) — lazy fastembed seam (`embed`/`dim`/`configured_dim`/`available`), env>config>default model precedence (`bge-small-en-v1.5`/384-dim), `[semantic]` pip extra; core install stays dep-free — v0.6 / Phase 9
- ✓ **VEC-01..03**: `memories_vec` vec0 store in `memory.db` keyed to rowid — embed-on-add/update/add_many (savepoint-atomic), lazy batch-capped backfill, dim-mismatch + load-failure degrade to FTS5; opening a store never loads the model or blocks startup — v0.6 / Phase 9
- ✓ **MEM-01..02**: semantic KNN in `MemoryStore.get_context()` — pure-semantic ranking over `memories_vec` with an L2 distance floor (`_SEMANTIC_MAX_DISTANCE`≈cosine 0.6) for the no-match case (NOT lexical fusion); byte-identical FTS5 fallback when no embedder/vectors; surfaces lexically-disjoint-but-semantically-relevant memories (the proven bench win) — v0.6 / Phase 10
- ✓ **WIKI-01..02**: per-run semantic top-k retrieval in the opt-in `context_prefix` wiki layer (`_semantic_wiki_layer`, ephemeral in-memory vec0 KNN over a `.planning/codebase/wiki/` corpus, k default 3); byte-identical default path + static `_read_wiki_layer` fallback when embedder/corpus absent; mechanism ready, corpus curation deferred (WIKI-F1) — v0.6 / Phase 11
- ✓ **HON-01..06 · MECH-01..03 · VEND-01..05 · GSD-01..05**: pipeline made honest (discipline can fail, orchestrator reads the audit, live-no-`claude` fails loud) and adapters made real (research groundedness measure→keep/discard, strategy scored rubric + verdict, discipline runs tests + real git/hook state); gstack (59) + superpowers (14) MIT skills vendored with `install-skills`; 51 MB lean full-parity GSD bundled and self-installing — v0.6.1 / Phases 12–15
- ✓ **HAR-01..05**: eval harness runs E2E and fails loud — mode-honest reporting (no cheap-mode caveat leak; reports state mode/arm/sample-size/producers), no silent no-op arms (absent producer → "arm measured nothing" + exit 3), memory→wiki distiller + article-corpus producer + one `prepare-fixture` path, seeded paired-bootstrap CI + one-command close-the-loop + CI-safe E2E smoke — v0.6.2 / Phases 16–18

### Active

<!-- v0.8.0 Harness Tax & Value (Phases 19–22, SEED-001). Fresh REQUIREMENTS.md generated by /gsd-new-milestone. -->

- [ ] **TAX-01..04**: real token/cost/latency accounting — `BridgeResult.usage` via the existing `output_format="json"` path (keeping `.output` byte-identical); `tokens_in/out/cache_read` + `wall_clock_s` in `RunSnapshot`; per-arm tokens/seconds in `bench/report.py`; cost-per-success denominator = `flowstate verify` acceptance gates. Deterministic, no LLM.
- [ ] **IND-01..03**: evaluator independence — fail loud when `--judge-model` is absent or equals the producer model; multi-judge averaging in `judge.py` (mirror `grounding.py`'s `--judge-models` majority vote + `_wilson`); `metrics.py` stays authoritative, judge stays excluded.
- [ ] **WIKI-03..06** *(activate the dormant WIKI-F1 layer)*: promote the memory→wiki distiller into production (manifest + staleness like `flowstate pack`); opt-in reader caller — a config flag makes `orchestrator.py`'s `build_context_prefix` pass `include_layers={"wiki"}`, byte-identical default when off, graceful degrade without `[semantic]`; dogfood smoke-test on FlowState as phase acceptance (layer demonstrably fires before any paid verdict).
- [ ] **VERD-01..03**: the verdict — pre-registered rules; paired-design run via `bench/close_loop.py` on a **real repo** across `none/pack/memory/wiki/full`, measuring the **compounding curve** (run 1 empty → wiki value appears run 2+); report quality **and** tax per arm. A null `wiki − none` is an accepted outcome (strip the layer).

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

- **v0.6.0 shipped & archived (Semantic Retrieval, 2026-07-10):** optional `[semantic]` fastembed extra + `memories_vec` vec0 store in `memory.db`; semantic KNN in `MemoryStore.get_context()` behind an L2 distance floor; per-run semantic top-k in the opt-in `context_prefix` wiki layer. 749 tests at 92.19%. Core install stays dep-free; all default paths byte-identical to v0.5.0. One deferred item (WIKI-F1 — dormant wiki mechanism, no production caller) carried to the ROADMAP Backlog.
- **Retrieval benchmarking arc (bench research tooling, 2026-07-09, post-v0.6.0):** real-data harnesses for LongMemEval (`bench/longmemeval.py`, session-level `recall_all@k`/`recall_any@k`) and LoCoMo (`bench/locomo.py`, evidence-coverage, `--corpus turns|observations`), sharing `bench/_retrieval.py` backends. Two harness bugs found and fixed: (1) whole-session embedding truncated 94.6% of sessions past bge's 512-token cap — fixed by `semantic_rank_chunked` (bge-small 0.806 → **0.866** `recall_all@5`); (2) LoCoMo retrieved over raw turns instead of the paper's observations corpus (semantic 0.327 → **0.459** full-cov@5). BM25 remains a strong baseline (0.844 / 0.481) and **has not been decisively beaten** — CIs overlap and no paired significance test has been run. See `bench/BENCHMARK_HANDOFF.md`.
- **Prompt-tuning A/B harness added (bench research tooling, 2026-06-29, post-v0.6.0):** three opt-in `bench/` rungs that tune prompts with *measured grounding* instead of vibes — `--mode promptab` (answer-instruction A/B, Wilson-CI-overlap gate), `--mode sysab` (strategy system-prompt A/B, pairwise position-debiased rubric judge, Wilson-vs-0.5 win-rate gate), and `bench/tune_loop.py` (mine the probes the live prompt fails → propose a candidate via one `claude` call → gate through `promptab` → emit a human-approval report). The "RSI arc": the gate disposes, a human approves the one change. ADD-ONLY, never-raises, stdlib+flowstate-only; **none of it runs in the deterministic pipeline** and `tune_loop` never edits source (no `--apply`, dedicated no-writes guard test). 803 tests at 92.19%. Quick tasks 260629-fxt / 260629-gzd / 260629-kyl.
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
| Prompt self-improvement lives in `bench/`, is eval-gated, and never auto-applies | RSI without a gate is drift, and wiring prompt self-modification into the deterministic runtime is exactly the surface FlowState avoids. The A/B harness *measures* (Wilson-CI gate), the tune-loop *proposes*, a human *approves* the one change — bench-only, no `--apply` | ✓ Validated (260629-fxt/gzd/kyl — `flowstate/` untouched + no-writes guard test; gate caught a real candidate regression in smoke testing) |
| Embedder ships as an optional `[semantic]` extra, never a core dep | fastembed pulls ~200MB of transitive deps + a model download on every install; the dep-free default install is a hard constraint. Optional extra + byte-identical FTS5 fallback preserves it | ✓ Validated (EMB-01..04, v0.6 — `import flowstate.embeddings` succeeds without fastembed) |
| Semantic no-match gated by an L2 **distance floor**, NOT an FTS5 pre-gate | An FTS5 gate would only fire semantic KNN when BM25 already matched — suppressing the lexically-disjoint-but-semantically-relevant case that is the entire point of the milestone. `_SEMANTIC_MAX_DISTANCE = 0.89` (≈ cosine 0.60) instead | ✓ Validated (MEM-01/02, v0.6 — caught as a **Critical** code-review finding and fixed before close; `10-01-SUMMARY.md` frontmatter still records the superseded gate decision, the code is authoritative) |
| Reranking / hybrid lexical+semantic fusion deferred out of v0.6 | Pure semantic KNN already recovered oracle-level grounding (0.825 ≈ 0.800) on the wiki bench; fusion is unjustified complexity **until measured to help** | — Pending (v0.7.0 exists to run exactly that measurement, on LongMemEval/LoCoMo, with stage-matched baselines) |
| **Adapters must be able to fail** (v0.6.1) | `discipline.py:56` hardcodes `success=True` and the orchestrator never reads the audit; research/strategy report success on total failure. A compounding loop can't compound if it can't tell success from failure, and benchmarking an enforcement layer that cannot fail measures nothing | — Pending (v0.6.1 Phase 12) |
| **REVERSED: bundle GSD full-runtime, don't detect/delegate** (v0.6.1, 2026-07-10) | Prior stance was "GSD stays detect-and-delegate; no cross-harness packaging." User directive: *"break my no cross-harness packaging… it should be there, by whatever legal means. I don't want to detect or prompt for it."* GSD is MIT (© Lex Christopherson) → vendor the pinned full runtime + `gsd-sdk` and install unconditionally. FlowState becomes a GSD redistributor and owns a version-pinned refresh path | — Pending (v0.6.1 Phase 15). Supersedes the delegate-only stance; does NOT reopen Codex/OpenCode/Cursor host adapters |

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
*Last updated: 2026-07-11 after v0.6.2 milestone — Make the Harness Real (Phases 16–18) archived to `milestones/v0.6.2-ROADMAP.md`; HON/MECH/VEND/GSD (v0.6.1) + HAR-01..05 (v0.6.2) moved to Validated; Active reset to v0.8.0 Harness Tax & Value (SEED-001, phases 19–22)*
