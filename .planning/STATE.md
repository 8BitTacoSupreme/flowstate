---
gsd_state_version: 1.0
milestone: v0.6.0
milestone_name: Semantic Retrieval
status: milestone_complete
stopped_at: Milestone complete (Phase 11 was final phase)
last_updated: 2026-06-18T20:17:19.328Z
last_activity: 2026-06-18
progress:
  total_phases: 3
  completed_phases: 3
  total_plans: 4
  completed_plans: 5
  percent: 100
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-18)

**Core value:** Each run starts smarter than the last — durable artifacts + auto-injected memory make work compound across runs.
**Current focus:** Milestone complete

## Current Position

Phase: 11
Plan: Not started
Status: Milestone complete
Last activity: 2026-07-08 - Completed quick task 260708-jy5: deterministic supersession in memory.py

Progress: [██████████] 100%

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

- [v0.6.0 roadmap]: Coarse granularity (3 phases) — single maintainer; phases 9/10/11 follow natural dependency boundary (foundation → memory seam → wiki seam)
- [v0.6.0 roadmap]: Phase 10 and 11 kept separate (not merged) — each maps to a distinct integration seam (memory.py vs context_prefix.py) that can be independently planned and verified
- [v0.6.0 roadmap]: Phase 10 and 11 both depend on Phase 9 only; Phase 11 does not depend on Phase 10 (parallel seams over the same vector foundation)
- [v0.6.0 roadmap]: Embedder is optional [semantic] extra — FTS5 fallback preserved on every path; default install stays dep-free; golden context_prefix tests must stay byte-identical
- [v0.6.0 roadmap]: Tests must inject a fake embed_fn (deterministic vectors) and skipif sqlite_vec — no model/network required; mirrors bench/grounding.py test patterns
- [v0.6.0 roadmap]: memory.db change is additive only (vec0 table + backfill); flowstate.json schema unchanged; no migration ladder bump needed
- [Phase ?]: rowid resolution pattern for vec0 embed-on-write
- [Phase ?]: enable_load_extension security re-scope after vec load

### Pending Todos

None yet.

### Blockers/Concerns

None at roadmap start. Key implementation constraint: every caller path must check embedder.available() before computing vectors — the FTS5 fallback is the correctness gate, not an afterthought. Confirm sqlite-vec loads cleanly on the existing MemoryStore._conn before Phase 9 planning.

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

## Session Continuity

Last session: 2026-07-09
Stopped at: Task D (260709-d64) complete. FINDINGS on real LongMemEval_S: RETRIEVAL (n=500) — FlowState semantic reaches BM25-parity with bge-base (recall_all@5 0.840≈BM25 0.844; recall_all@10 0.930>0.904); bge-small (33M) 0.806. QA (n=100 representative): claude judge retrieval 0.450/oracle 0.410; gpt-4-turbo judge retrieval 0.410/oracle 0.480 (restored oracle>retrieval). Judge swap barely moved it → the gap to paper's 0.870 oracle is the READER (claude sonnet + generic prompt + truncation), not retrieval/judge. Discovered key's project lacks gpt-4o access (only gpt-3.5/gpt-4-turbo) — silent 0/100 bug fixed by Task D canary. bge-base embed on CPU is slow (~30-40min/500).
Resume file: None
Next step: Improved-QA reruns (bge-base, sample 100, tuned reader): (a) claude reader + gpt-4-turbo judge, (b) gpt-4-turbo reader + gpt-4-turbo judge — does tuned/stronger reader lift oracle 0.48→toward 0.87? Then push batch (held). Rotate the OPENAI_API_KEY that was pasted in chat.
