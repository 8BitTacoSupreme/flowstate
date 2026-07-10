---
gsd_state_version: 1.0
milestone: v0.7.0
milestone_name: Retrieval Benchmark Rigor
status: planning
last_updated: "2026-07-10T15:00:00.000Z"
last_activity: 2026-07-10
progress:
  total_phases: 6
  completed_phases: 0
  total_plans: 0
  completed_plans: 0
  percent: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-07-10)

**Core value:** Each run starts smarter than the last — durable artifacts + auto-injected memory make work compound across runs.
**Current focus:** Phase 12: Falsifiable Measurement (v0.7.0 Retrieval Benchmark Rigor)

## Current Position

Phase: 12 of 17 (Falsifiable Measurement)
Plan: — (not yet planned)
Status: Ready to plan
Last activity: 2026-07-10 — Completed quick task 260710-ffo: corrected the benchmarking record (bench/BENCHMARKING_SCOPE.md + PAIRED_DESIGN_RUNBOOK.md)

## Performance Metrics

**Velocity:**

- Total plans completed: 15
- Average duration: ~15 min/plan
- Total execution time: ~2.5 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 06 | 3 | - | - |
| 07 | 4 | - | - |
| 08 | 3 | - | - |
| 09 | 2 | - | - |
| 10 | 1 | - | - |
| 11 | 2 | - | - |

**Recent Trend:**

- Last 5 plans: 266s, 8m, 189s, 35s, 20m
- Trend: Stable

*Updated after each plan completion*
| Phase 09 P01 | 281 | 2 tasks | 3 files |
| Phase 09 P02 | 420 | 2 tasks | 2 files |
| Phase 11-semantic-wiki-retrieval P01 | 25 | 2 tasks | 2 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [v0.7.0 roadmap]: Phase order is measurement-first — Phase 12 (dumps + significance tests + stratified split) lands before any config change, so every later phase's claims are falsifiable from the start rather than retrofitted
- [v0.7.0 roadmap]: Coarse granularity (6 phases, 12-17) — dependency chain is strictly linear (12→13→14→15→16→17) except Phase 16, which depends on 13 (prefix/cache) and reuses Phase 15's `rerank()`, but not Phase 14's chunk/rollup sweep (LoCoMo docs are short, never chunked)
- [v0.7.0 roadmap]: RERANK-01 is a hard gate inside Phase 15 — the cross-encoder (RERANK-02/03) is only built if the pool-ceiling analysis from Phase 12's dumps justifies it; a failed gate is a valid phase outcome, not a blocker
- [v0.7.0 roadmap]: Test split is touched exactly once, in Phase 17, after the config is frozen on dev-200 in Phase 14 — prevents tuning-on-test
- [v0.7.0 roadmap]: `bench/grounding.py` stays ADD-ONLY across all 6 phases; the query/document embedder interface and cache land in `bench/_retrieval.py`/`bench/_embed_cache.py` instead
- [v0.6.0 roadmap]: Coarse granularity (3 phases) — single maintainer; phases 9/10/11 follow natural dependency boundary (foundation → memory seam → wiki seam)
- [v0.6.0 roadmap]: Phase 10 and 11 kept separate (not merged) — each maps to a distinct integration seam (memory.py vs context_prefix.py) that can be independently planned and verified
- [v0.6.0 roadmap]: Phase 10 and 11 both depend on Phase 9 only; Phase 11 does not depend on Phase 10 (parallel seams over the same vector foundation)
- [v0.6.0 roadmap]: Embedder is optional [semantic] extra — FTS5 fallback preserved on every path; default install stays dep-free; golden context_prefix tests must stay byte-identical
- [Phase ?]: rowid resolution pattern for vec0 embed-on-write
- [Phase ?]: enable_load_extension security re-scope after vec load

### Pending Todos

None yet.

### Blockers/Concerns

- **SECURITY (carried forward, unresolved):** an `OPENAI_API_KEY` was pasted into a chat session during the v0.6.0-era benchmark work. Rotate it if that has not already been done. Tracked here so the milestone reset does not erase it.
- **Benchmark integrity:** `bench/BENCHMARK_HANDOFF.md` §4 records that `_READER_INSTRUCTION` is a measured QA regression that is still the default reader prompt. Out of scope for v0.7.0 (retrieval-only), but no QA number should be quoted until it is addressed.

## Quick Tasks Completed

| Task ID | Name | Status | Completed | Commits |
|---------|------|--------|-----------|---------|
| 260618-p97 | Wire RGB four axes into bench/grounding.py | complete | 2026-06-18 | 5f56e6d, a194431, 137595e, da6a9d6, 32a0df7 |
| 260619-nfe | Add opt-in hard-negative distractor selection to RGB axes | complete | 2026-06-19 | 484b433, 00ab722, cb67d45, 831def6 |
| 260629-fxt | Add --mode promptab (eval-gated answer-instruction A/B) to bench/grounding.py | complete | 2026-06-29 | 2ff1d63, 03c07ae |
| 260629-gzd | Add --mode sysab (system-prompt A/B for strategy adapter, pairwise rubric judge, Wilson-vs-0.5 gate) | complete | 2026-06-29 | 0523a6b, 18bae30 |
| 260629-kyl | Build bench/tune_loop.py — manual prompt-tuning loop (mine→propose→gate→human-approval report; never edits source) | complete | 2026-06-29 | 20a0afd, a22087d |
| 260708-jy5 | Deterministic supersession in memory.py (additive superseded_by column, supersede() API, retrieval excludes superseded by default, flag-only find_contradiction_candidates) | complete | 2026-07-08 | 35f3a61, 7a467d9 |
| 260708-mjt | Build bench/longmemeval.py + bench/locomo.py retrieval-eval harnesses (recall_all/any@k, evidence-coverage, semantic vs BM25, Wilson CIs, smoke fixtures) — Task A of the public-benchmark arc | complete | 2026-07-08 | b1d962c, fcb87ef, d6a6704 |
| 260708-nsm | Build bench/longmemeval_qa.py — QA-accuracy layer (Task B): retrieve→read→judge, per-question-type + overall accuracy with Wilson CIs, retrieval+oracle arms, --limit | complete | 2026-07-08 | 603d558, 1087dce, 830c6e9 |
| 260708-r6n | Add GPT-4o judge provider (--judge-provider openai, hard-error if unavailable) + representative seeded sampling (--sample/--seed) to longmemeval_qa.py; openai as optional [eval] extra | complete | 2026-07-08 | ee80b24, 5c9928b, 50483e0 |
| 260709-d64 | Reader-path + robustness for longmemeval_qa.py: LongMemEval-tuned reader prompt, --reader-provider claude|openai, upfront openai canary (fail loud on model-403 instead of silent 0/100) | complete | 2026-07-09 | 66cf980, 1747290 |
| 260709-fot | Task E: OpenAI rate-limit resilience for longmemeval_qa.py — SDK retry client (max_retries=10/timeout=120) + mass-failure guard (>--max-failure-rate of judge/reader None → unreliable flag + exit 2, never fake a low score) | complete | 2026-07-09 | 7596a75, 1dd0d9c |
| 260709-j8q | Build bench/locomo_qa.py — LoCoMo QA-accuracy layer (official stemmed-F1 + exact-match, no LLM judge; per-category 1-5 + Wilson CI; adversarial rule; retrieval+oracle arms; reader claude|openai w/ Task E resilience) | complete | 2026-07-09 | 5067807, 597579e |
| 260709-qte | Chunk-level semantic retrieval (semantic_rank_chunked + --chunk-tokens): fixes measured truncation — 94.6% of LongMemEval sessions exceed bge 512-tok cap (median 2500 tok) | complete | 2026-07-09 | 7a67cec, 585ae5e |
| 260709-rep | Add --corpus turns|observations arm to bench/locomo.py (paper's best RAG corpus; observation docs carry dia_id provenance; summaries excluded — no provenance) | complete | 2026-07-09 | a07259b, 2fb5113 |
| 260710-ffo | Correct the benchmarking record — new bench/BENCHMARKING_SCOPE.md (two-track model: Track 1 retrieval/deterministic where BM25 is the incumbent counterfactual, vs Track 2 harness-value; dead-alias debunk of autoresearch/gstack/superpowers) + fix stale PAIRED_DESIGN_RUNBOOK.md (prereqs #1/#2 LANDED, #3 unbuilt; pack≈none vs wiki 0.825≈oracle) | complete | 2026-07-10 | 9790284, c268cc9, e61ebe1 |

## Session Continuity

Last session: 2026-07-10
Stopped at: ROADMAP.md, STATE.md, and REQUIREMENTS.md traceability written for v0.7.0 (Phases 12-17, 18/18 requirements mapped, 100% coverage). No phase planning started yet.

**Established facts for v0.7.0 (verified this session, not estimates):**
- `recall_any@5` = 0.966 for **both** BM25 and chunked-semantic; `recall_all@5` = 0.866 vs 0.844; `recall_all@10` = 0.946 vs 0.904. Gold sessions are already retrieved, at ranks 6–10 → a **ranking** problem. A perfect reranker over a top-R pool scores exactly `recall_all@R`, so dense→rerank@10 caps at 0.946 and BM25→rerank@10 caps at 0.904.
- The 0.866-vs-0.844 lead is **not currently testable**: both harnesses emit only aggregate means + Wilson CI, no per-instance records. McNemar flips around b+c ≈ 27 discordant pairs — it could land either side of p<0.05.
- LongMemEval-S is **type-blocked** (6 `question_type`s in 7 contiguous runs). `--limit 100` yields 70 `single-session-user` + 30 `multi-session` and zero temporal-reasoning/knowledge-update. Every historical `--limit` run was on a biased subset. Use stratified sampling.
- `|gold|` reaches 6 (3 instances), so `recall_all@5` has a structural ceiling of **0.994**, not 1.0. 0 abstentions in the file.
- `bench/grounding.py::_default_embedder` calls `model.embed()` for docs *and* queries; fastembed's `query_embed()` is a no-op passthrough → BGE's query instruction prefix is **never applied**. Free win, needs an `embed_fn` interface change (build it in `_retrieval.py`; grounding.py is ADD-ONLY).
- fastembed L2-normalizes (`_post_process_onnx_output` → `normalize()`), so `semantic_rank`'s L2 ordering ≡ cosine ordering. **Not a bug** — don't spend time there.
- Installed fastembed 0.8 ships cross-encoders (`Xenova/ms-marco-MiniLM-L-6-v2` 80MB, `jinaai/jina-reranker-v1-turbo-en` 150MB, `BAAI/bge-reranker-base` 1.04GB) and 8192-token embedders (`jina-embeddings-v2-base-en`, `nomic-embed-text-v1.5-Q` 130MB). **Zero new deps needed.**
- LoCoMo currently **loses** to BM25 on semantic full-cov@5 (0.459 vs 0.481) — Phase 16 needs to report this honestly per-category, not paper over it.

Resume file: None (roadmap approved this session)
Data: `data/longmemeval_s_cleaned.json` (265MB) + `data/locomo10.json` present; `data/` is now gitignored (LoCoMo is CC BY-NC).
Next step: `/gsd-plan-phase 12` — per-instance dumps + `bench/stats.py` + `compare.py` + stratified split. Phase 12 may kill the current headline claim; that is its purpose.

## Operator Next Steps

- Plan the first v0.7.0 phase with `/gsd-plan-phase 12`
- Rotate the `OPENAI_API_KEY` pasted in an earlier chat session, if not already done
</content>
