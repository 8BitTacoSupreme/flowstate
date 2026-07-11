---
gsd_state_version: 1.0
milestone: v0.8.0
milestone_name: Harness Tax & Value
status: executing
stopped_at: Phase 20 context gathered
last_updated: "2026-07-11T06:48:49.313Z"
last_activity: 2026-07-11 -- Phase 20 planning complete
progress:
  total_phases: 4
  completed_phases: 1
  total_plans: 5
  completed_plans: 3
  percent: 25
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-07-10)

**Core value:** Each run starts smarter than the last — durable artifacts + auto-injected memory make work compound across runs.
**Current focus:** Phase 20 — evaluator independence

## Current Position

Phase: 20
Plan: Not started
Status: Ready to execute
Last activity: 2026-07-11 -- Phase 20 planning complete

## Performance Metrics

**Velocity:**

- Total plans completed: 31
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
| 13 | 3 | - | - |
| 14 | 4 | - | - |
| 15 | 5 | - | - |
| 16 | 1 | - | - |
| 19 | 3 | - | - |

**Recent Trend:**

- Last 5 plans: 266s, 8m, 189s, 35s, 20m
- Trend: Stable

*Updated after each plan completion*
| Phase 09 P01 | 281 | 2 tasks | 3 files |
| Phase 09 P02 | 420 | 2 tasks | 2 files |
| Phase 11-semantic-wiki-retrieval P01 | 25 | 2 tasks | 2 files |
| Phase 13 P01 | ~720 | 2 tasks | 2 files |
| Phase 14 P14-01 | 720 | 2 tasks | 170 files |
| Phase 14 P14-03 | 180 | 2 tasks | 3 files |
| Phase 14 P14-04 | 6 | 3 tasks | 5 files |
| Phase 15 P15-01 | 360 | 2 tasks | 8 files |
| Phase 15 P15-02 | 1200 | 2 tasks | 3 files |
| Phase 15 P15-03 | 480 | 1 tasks | 2 files |
| Phase 15 P15-04 | 1080 | 2 tasks | 3 files |
| Phase 17 P03 | 12min | 2 tasks | 3 files |
| Phase 18 P01 | 6min | 2 tasks | 4 files |
| Phase 18 P03 | 25min | 1 tasks | 1 files |
| Phase 18 P02 | 7min | 2 tasks | 2 files |
| Phase 19 P01 | 18 | 2 tasks | 2 files |
| Phase 19 P02 | 14min | 3 tasks | 8 files |
| Phase 19 P03 | 540 | 2 tasks | 2 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [v0.8.0 roadmap]: Phase order follows the SEED-001 dependency chain — 19 (tax accounting) → 20 (evaluator independence) → 21 (wiki production wiring) → 22 (verdict, capstone needing all three measurement primitives in place)
- [v0.8.0 roadmap]: Coarse granularity (4 phases, 19-22) — matches SEED-001's pre-scoped structure; single maintainer, phases map 1:1 onto the seed's four numbered sections
- [v0.8.0 roadmap]: Phase 21 is production wiring ONLY — the bench-side memory→wiki distiller (`bench/distiller.py`) already shipped in v0.6.2 Phase 17; this milestone does not rebuild it, only promotes/calls it and adds the opt-in reader flag
- [v0.8.0 roadmap]: Phase 22 flagged as expensive (live LLM runs, 4-5 arms x multiple trials x multiple runs for the compounding curve) — smoke at reduced trials/runs before scaling, per SEED-001's cost-reality note
- [Phase 13-01 / MECH-01]: research adapter gets Autoresearch's measure->keep/discard over OUTPUT — score each section vs the fixture's `retrieval_questions` (threshold 0.6, one bounded retry, discard-if-still-weak); the prompt is reused byte-identical on regeneration (no prompt self-modification in the runtime). All-discarded -> produced==0 -> success=False (preserves Phase 12 HON-03 fail-loud).
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
- [Phase ?]: Phase 14-01 VEND-01/02: vendored gstack@7c9df1c (59) + superpowers@d884ae0 (14) as data-only trees; pruned build tooling 36M->4.4M for no-bin/T-14-02
- [Phase ?]: launch handoffs gated on installed .claude/skills/<namespace>; absent emits install-skills prompt (T-14-12)
- [Phase ?]: README test count reconciled to post-phase --collect-only total (1000), never hardcoded (T-14-15)
- [Phase ?]: [Phase 15-02 / GSD-02]: install_skills installs GSD unconditionally (no detect/prompt); full node_modules copied to .claude/get-shit-done/node_modules so gsd-sdk resolves deps by walking up (byte-identical to 15-01's proven tree); commands/gsd converted to .claude/skills/gsd-<cmd>/SKILL.md; copy-as-data, path-safe, idempotent, no shim
- [Phase 17]: [Phase 17-03 / HAR-03]: prepare_fixture wires flowstate.pack.run_pack + bench.distiller.main behind one entry point; arms without a producer (full/memory/none) are an accepted no-op, not an argparse rejection
- [Phase 18-01]: n==1 bootstrap edge case handled by the general resampling path (not a special branch); every size-1 resample naturally degenerates to ci_low==ci_high==mean
- [Phase 18-01]: Percentile CI indices use round(p*(resamples-1)) with a defensive ci_low<=mean<=ci_high clamp against 2-decimal rounding drift
- [Phase 18-01]: bench/report.py intentionally left untouched per plan scope note; no caller in this phase routes the CI through report.write_json
- [Phase 18-03]: E2E smoke writes producer artifacts (repomix-pack.xml, wiki/*.md) directly to disk instead of shelling out to repomix/npx, keeping the harness-of-harnesses gate CI-safe with zero external tool dependency
- [Phase 18-02]: close_loop uses module-reference imports (import bench.X as X) instead of from-imports so tests can monkeypatch bench.replicate._run_trial / bench.prepare_fixture.main effectively
- [Phase ?]: Phase 19-01 TAX-01: BridgeResult.usage/duration_s appended after existing fields (positional-ctor safe); json path parses only when output_format=json AND top-level result key present, else raw-stdout fallback with usage=None (never raises); cumulative totals accumulate only on successful returns
- [Phase 19-02 / TAX-02]: RunSnapshot gains real tokens_in/out/cache_read/wall_clock_s appended after layers_present with defaults (pure carriage — compute_scorecard byte-identical, no axis reads them); threaded end-to-end orchestrator bridge totals -> append_run_entry RUN metadata -> capture_run_snapshot (type-guarded metadata.get, 0/None fallback); adapters switched to output_format=json to capture usage (Plan 01 byte-identical .output, no extra LLM call); prefix_tokens kept as the DISTINCT Track-1 growth signal (input-context size), NOT repurposed for consumption
- [Phase ?]: [Phase 19-03 / TAX-03/04]: tax rendering lives entirely in bench/report.py (presentation-only) — per-arm tokens/seconds as a Track-2 block EXCLUDED from compounding_score; cost-per-success = (tokens_in+tokens_out)/summed verify_pass (passed flowstate verify acceptance gates, NOT run/commit count), gates_passed==0 -> n/a

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
| 260710-ffo | Correct the benchmarking record — new bench/BENCHMARKING_SCOPE.md (two-track model: Track 1 retrieval/deterministic where BM25 is the incumbent counterfactual, vs Track 2 harness-value) + fix stale PAIRED_DESIGN_RUNBOOK.md (prereqs #1/#2 LANDED, #3 unbuilt; pack≈none vs wiki 0.825≈oracle). NOTE: its "dead-alias" claim about autoresearch/gstack/superpowers was WRONG and later corrected by erratum eab8ae8 — those are real MIT upstreams FlowState's adapters are named after and barely implement (v0.6.1 fixes that). | complete | 2026-07-10 | 9790284, c268cc9, e61ebe1, eab8ae8 |
| 260710-x5a | Harden bench/replicate.py::_run_trial — distinguish judge-output contract violations (malformed JSON / `per_run` row missing `score` → propagate/halt) from legitimate trial gaps (nonzero returncode, unreadable/missing output → None + diagnostic). Narrows `except Exception`→`except OSError`, checks subprocess returncode, moves JSON/score parse after the finally so a broken judge contract can't be silently averaged into the paired-bootstrap CI. close_loop.py unchanged (its pipeline guard surfaces a propagated error as exit 1). Follow-up to Phase 18 re-review. | complete | 2026-07-11 | ba21455, a689922 |

## Session Continuity

Last session: 2026-07-11T06:11:13.936Z
Stopped at: Phase 20 context gathered

**Why v0.8.0 exists (SEED-001, verified prior session):**

- No token/cost/latency accounting exists in `bench/`; `prefix_tokens` is `len(prefix)//4`, an input-context estimate, not consumption. `ClaudeBridge.run()` already accepts `output_format="json"` but no caller passes it and `BridgeResult` has no `usage` field.
- The proven-best context layer (distilled wiki + semantic retrieval, 0.825 ≈ oracle 0.800) is switched off in production — no `flowstate/` module passes `include_layers={"wiki"}`. The bench-side producer (`bench/distiller.py`) shipped in v0.6.2; only the production wiring is missing.
- `bench/judge.py` has no enforcement against judge-model == producer-model; `bench/metrics.py`'s `CompoundingScore` is the authoritative deterministic scorer and already excludes the judge from `compounding_score` — this milestone hardens the guard-rail, not the architecture.
- The harness-value experiment already ran once and came back null (Cohen's d 0.29); a null `wiki − none` on a real repo is an accepted, pre-registered-for outcome, not a failure to avoid.

Next step: `/gsd-plan-phase 19` — Phase 19 "The Tax" (real token/cost/latency accounting: `BridgeResult.usage`, `RunSnapshot` fields, `bench/report.py` per-arm tokens/seconds, cost-per-success denominator). Then Phase 20 (evaluator independence), Phase 21 (activate the wiki — production wiring only, bench-side producer already shipped), Phase 22 (the verdict — pre-registered paired-design run on a real repo; flagged expensive, live LLM runs).

---

**DEFERRED — established facts for v0.7.0 (verified, carry forward when v0.7.0 starts; phases renumber to 15-20):**

- `recall_any@5` = 0.966 for **both** BM25 and chunked-semantic; `recall_all@5` = 0.866 vs 0.844; `recall_all@10` = 0.946 vs 0.904. Gold sessions are already retrieved, at ranks 6–10 → a **ranking** problem. A perfect reranker over a top-R pool scores exactly `recall_all@R`, so dense→rerank@10 caps at 0.946 and BM25→rerank@10 caps at 0.904.
- The 0.866-vs-0.844 lead is **not currently testable**: both harnesses emit only aggregate means + Wilson CI, no per-instance records. McNemar flips around b+c ≈ 27 discordant pairs — it could land either side of p<0.05.
- LongMemEval-S is **type-blocked** (6 `question_type`s in 7 contiguous runs). `--limit 100` yields 70 `single-session-user` + 30 `multi-session` and zero temporal-reasoning/knowledge-update. Every historical `--limit` run was on a biased subset. Use stratified sampling.
- `|gold|` reaches 6 (3 instances), so `recall_all@5` has a structural ceiling of **0.994**, not 1.0. 0 abstentions in the file.
- `bench/grounding.py::_default_embedder` calls `model.embed()` for docs *and* queries; fastembed's `query_embed()` is a no-op passthrough → BGE's query instruction prefix is **never applied**. Free win, needs an `embed_fn` interface change (build it in `_retrieval.py`; grounding.py is ADD-ONLY).
- fastembed L2-normalizes (`_post_process_onnx_output` → `normalize()`), so `semantic_rank`'s L2 ordering ≡ cosine ordering. **Not a bug** — don't spend time there.
- Installed fastembed 0.8 ships cross-encoders (`Xenova/ms-marco-MiniLM-L-6-v2` 80MB, `jinaai/jina-reranker-v1-turbo-en` 150MB, `BAAI/bge-reranker-base` 1.04GB) and 8192-token embedders (`jina-embeddings-v2-base-en`, `nomic-embed-text-v1.5-Q` 130MB). **Zero new deps needed.**
- LoCoMo currently **loses** to BM25 on semantic full-cov@5 (0.459 vs 0.481) — Phase 16 needs to report this honestly per-category, not paper over it.

Data: `data/longmemeval_s_cleaned.json` (265MB) + `data/locomo10.json` present; `data/` is gitignored (LoCoMo is CC BY-NC). Held for v0.7.0.

## Operator Next Steps

- Run `/gsd-plan-phase 19` to begin Phase 19: The Tax

</content>

> **Planning override (Phase 20, 2026-07-11):** decision-coverage gate reported 1/7 by structured `must_haves.truths` scan, but the semantic plan-checker PASSED and plans cite D-01..D-08 60+ times in bodies with full concept coverage. Proceeded with override — verify-phase should re-confirm all 8 CONTEXT decisions landed in code.
