---
gsd_state_version: 1.0
milestone: v0.5.0
milestone_name: Compounding Loop
status: Awaiting next milestone
stopped_at: Completed 08-01-PLAN.md — VerifyResult + checker registry + run_verify; 19 tests at 92% coverage
last_updated: "2026-06-09T15:06:03.914Z"
last_activity: 2026-06-09 — Milestone v0.5.0 completed and archived
progress:
  total_phases: 3
  completed_phases: 3
  total_plans: 10
  completed_plans: 10
  percent: 100
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-06)

**Core value:** Each run starts smarter than the last — durable artifacts + auto-injected memory make work compound across runs.
**Current focus:** Milestone complete

## Current Position

Phase: Milestone v0.5.0 complete
Plan: —
Status: Awaiting next milestone
Last activity: 2026-06-15 — Completed quick task 260615-d4p: wiki arm (distilled-CAG) + judge retry

## Performance Metrics

**Velocity:**

- Total plans completed: 10
- Average duration: -
- Total execution time: 0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| Phase 03 P01 | 9m | 3 tasks | 7 files |
| Phase 04 P01 | 11m | 3 tasks | 6 files |
| 06 | 3 | - | - |
| 07 | 4 | - | - |
| 08 | 3 | - | - |

**Recent Trend:**

- Last 5 plans: -
- Trend: -

*Updated after each plan completion*
| Phase 02 P04 | 3m24s | 2 tasks | 4 files |
| Phase 02 P01 | 12min | 3 tasks | 8 files |
| Phase 02 P03 | 4min | 2 tasks | 5 files |
| Phase 02 P02 | 6min | 3 tasks | 6 files |
| Phase 03 P02 | 5m | 1 tasks | 2 files |
| Phase 03 P03 | 7m | 2 tasks | 3 files |
| Phase 06 P01 | 266 | 3 tasks | 6 files |
| Phase 06 P02 | 8m | 2 tasks | 3 files |
| Phase 06 P03 | 189 | 2 tasks | 2 files |
| Phase 07 P03 | 35 | 2 tasks | 2 files |
| Phase 07-gotchas-accumulator P04 | 20min | 2 tasks | 6 files |
| Phase 08-runnable-verification P01 | 35min | 2 tasks | 2 files |
| Phase 08 P02 | 155 | 2 tasks | 2 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- Coarse granularity (2 phases): single maintainer, bounded scope, "one small phase" framing for operate-safely
- Land pivot before new surface: compounding unstaged work with new features makes diffs unreviewable
- Hook gating via env var (not config file): matches ECC FLOWSTATE_HANDLERS pattern, avoids new config surface
- Borrow install-manifest from ECC: `flowstate fresh` is currently destructive without knowing what it owns
- [Phase 02]: Per-call env-var lookup over module-level cache for handler gating — easiest to monkeypatch, no stale state
- [Phase 02]: Disabled-names denylist takes precedence over profile rank — explicit override semantics
- [Phase 02]: InstallEntry uses Literal[5 kinds] for Pydantic kind validation — catches typos at write time, not at fresh time
- [Phase 02]: checksum=None semantically means mutable file (memory.db) — _verify_checksum returns True for None, skipping verification
- [Phase 02]: Orphan scan bounded to .planning/, research/, memory.db, flowstate.json — .claude/ and source never candidates (safe-by-default)
- [Phase 02]: Status renderer is a pure function: state + root in, str out; never raises on missing files (memory.db, ROADMAP.md absent → graceful fallback)
- [Phase 02]: click.echo (not console.print) for raw markdown + 'Wrote:' path output — Rich soft-wraps long absolute paths and breaks pipe friendliness
- [Phase 02]: MemoryStore.last_entry_at() public helper replaces ad-hoc store._conn.execute(...) from outside — encapsulation boundary preserved
- [Phase 02]: Late-binding run_doctor checks via import-self pattern — makes module-level checks monkeypatchable from within the same module
- [Phase 02]: Pydantic-immutable-safe checksum updates via entry.model_copy(update={...}) + rebuilt list, NOT in-place attribute assignment
- [Phase 02]: Safe vs destructive repair split: orphan deletion + corrupt-db recreation require explicit --apply-destructive flag
- [Phase 02]: CliRunner env-isolation via monkeypatch.setenv (writes to os.environ) — avoids env= per-invoke plumbing (plan-checker W4)
- [v0.4.0 roadmap]: Coarse granularity (3 phases) — single maintainer; phases 3/4/5 follow natural dependency boundary (ingredients → compose → UX)
- [v0.4.0 roadmap]: Phase 5 depends on Phase 4 softly — kickoff reuses pack+fixture scaffold from Phases 3-4, but DX-01 (SUMMARY frontmatter) is independent
- [Phase 03 P01]: _find_repomix mirrors _find_claude: FLOWSTATE_REPOMIX_BIN env var > PATH shutil.which > candidate paths
- [Phase 03 P01]: run_pack imports _register from context.py at call-time (lazy) to avoid circular import at module level
- [Phase 03 P01]: is_pack_stale uses entry.created_at.timestamp() vs max(*.py mtime); no py files = not stale
- [Phase 03 P01]: _make_bridge passes allowed_tools=['mcp__repomix'] as kwargs alongside project_root — single construction site, explicit override
- [Phase 03 P01]: v0.3.0->v0.4.0 migration guard fixed from '>= 0.3.0' to '>= 0.4.0' so 0.3.0 state flows into migration ladder
- [Phase 03 P02]: CANON constant placed before _SENTINEL at module level; inject_canon=True default covers all callers without opt-in
- [Phase 03 P02]: final_system.strip() guard ensures --system-prompt omitted when inject_canon=False and no system_prompt
- [Phase 03 P02]: CANON text lifted verbatim from /Users/jhogan/CLAUDE.md §1-4; no paraphrase
- [Phase 03 P03]: generate_starter_fixture is a pure function (no I/O) matching existing generate_* style
- [Phase 03 P03]: write_context_files count grows 5→7; .mcp.json included in state.context_files via shared created-list assignment
- [Phase 03 P03]: DX-02 guidance appended to generate_claude_md dedent template as ## Repomix Pack section
- [Phase 04 P01]: build_context_prefix() assembles fixtures → pack(fit-ladder) → memory; built once in orchestrator, threaded via prior_knowledge seam (CAG-01)
- [Phase 04 P01]: _estimate_tokens replicates len(text)//4 from memory.py — no cross-module import of private helper
- [Phase 04 P01]: context_prefix.py imports from flowstate.pack but NEVER from flowstate.bridge — canon exclusion is a hard module boundary
- [Phase 04 P01]: ENABLE_PROMPT_CACHING_1H is default-False BridgeConfig flag; no unconditional injection (API-key-tier feature)
- [v0.5.0 roadmap]: Coarse granularity (3 phases) — single maintainer; phases 6/7/8 follow natural dependency boundary (journal → gotchas → verify closes the loop)
- [v0.5.0 roadmap]: Phase 7 depends on Phase 6 — both add a new MemoryKind and a new build_context_prefix layer; sharing the layering pattern makes Phase 6 the natural prerequisite
- [v0.5.0 roadmap]: Phase 8 depends on both 6 and 7 — verify failures must feed GOT-01 (Phase 7) and RUN-01 (Phase 6) to close the compounding loop
- [v0.5.0 roadmap]: `## Gotchas` layer placed BEFORE memory (cache-friendlier, near fixtures); `## Since Last Run` placed AFTER memory (most-dynamic, must stay outside cache window)
- [v0.5.0 roadmap]: Journal + gotchas are pure-Python derivations of run state — no bridge calls; keeps them cheap, reproducible, and cache-neutral
- [Phase ?]: [Phase 06 P02]: Layer 4 (since-last-run) after memory — most-dynamic-last for cache efficiency
- [Phase ?]: [Phase 06 P02]: run_journal_prefix_entries defaults to 3; isinstance(int) and >0 guard mirrors _load_budget
- [Phase ?]: [Phase 06 P02]: No bridge import in context_prefix.py — hard module boundary preserved through RUN-02
- [Phase ?]: [Phase 06 P03]: journal command under @main (not memory group) for top-level discoverability; try/except wraps full MemoryStore open+read for corrupt-DB graceful degrade
- [Phase ?]: [Phase 07 P04]: Lazy import of capture_gotcha inside on_step_failed avoids circular import (gotchas->memory<-memory_handlers)
- [Phase ?]: [Phase 07 P04]: Journal gotchas slot queries INSIGHT entries by run_id in-band — no threading needed through append_run_entry call site
- [Phase ?]: [Phase 07 P04]: harvest_planning_gotchas placed after MemoryStore opens, before interview answer seeding — prior-phase artifacts available to all adapters
- [Phase ?]: SKIP (not FAIL) for NL acceptance_gates and forbidden_actions — honest about mechanical vs manual verifiability

### Pending Todos

None yet.

### Blockers/Concerns

None at roadmap start. Implementation order matters: MemoryKind.RUN must be added before Phase 6 plans can write journal entries; MemoryKind.INSIGHT (tagged `gotcha`) already exists but the capture hooks do not — confirm existing MemoryKind values before Phase 7 planning.

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 260525-m9v | Unify memory injection at orchestrator (CAG-inspired, arXiv 2412.15605) | 2026-05-25 | 27708c5 | [260525-m9v-unify-memory-injection-at-orchestrator-b](./quick/260525-m9v-unify-memory-injection-at-orchestrator-b/) |
| 260525-o6h | Spike: confirm `claude --print` prompt cache fires (-32% wall, -37% API on call 2) | 2026-05-25 | 996049b | [260525-o6h-spike-confirm-claude-print-server-side-p](./quick/260525-o6h-spike-confirm-claude-print-server-side-p/) |
| 260609-j0g | Phase A intrinsic compounding eval harness (`bench/` package: 4-axis scorecard, cheap/real modes, temp-isolated runner) — measures "run N+1 beats run N"; 42 bench tests, reviewed + fixed (3 HIGH incl. in-place-mutation + inert-axes) | 2026-06-09 | 0e2071b | [260609-j0g-build-phase-a-intrinsic-compounding-eval](./quick/260609-j0g-build-phase-a-intrinsic-compounding-eval/) |
| 260613-ga5 | Per-layer context-prefix toggle + paired-design bench wiring (runbook Phase 1) — additive `include_layers` kwarg (assembly-time gating, byte-identical default); `--inject on\|off`→`--layers {full,none,pack,memory}`; replicate multi-arm + `--paired` run-0 normalization + per-arm Cohen's d vs `none`; 622 tests @ 92% | 2026-06-13 | 6a7f03a | [260613-ga5-per-layer-context-prefix-toggle-paired-d](./quick/260613-ga5-per-layer-context-prefix-toggle-paired-d/) |
| 260613-hk2 | Real-repo scaffold preservation (Phase 3 prereq) — `scaffold(root, *, synthetic=True)`; `synthetic=False` preserves kickoff prep (config/budget, real fixtures, pack, PROJECT/ROADMAP, research/, .claude/) and only resets memory.db; `_real_loop` now uses synthetic=False. Unblocks real-repo runs (synthetic scaffold was wiping budget→pack-drop + replacing the judge rubric); 626 tests @ 92% | 2026-06-13 | 7e2e768 | [260613-hk2-real-repo-scaffold-preservation-for-the-](./quick/260613-hk2-real-repo-scaffold-preservation-for-the-/) |
| 260613-m60 | Research-adapter call resilience — `max_turns` 3→6 + bounded 3-attempt retry per topic in `ResearchAdapter.execute` (success = `br.success and br.output.strip()`; placeholder only after all attempts fail). Fixes flaky "Error: Reached max turns (3)" (~40% rate w/ WebSearch) that gutted reports and made the bench's no-context arm spuriously out-score pack/full; 635 tests @ 92% | 2026-06-13 | 0daf044 | [260613-m60-research-adapter-call-resilience-raise-m](./quick/260613-m60-research-adapter-call-resilience-raise-m/) |
| 260615-d4p | Wiki arm (distilled-CAG) + judge retry — opt-in `wiki` layer in context_prefix (fixtures→wiki→pack; byte-identical default preserved via separate gate), `--layers wiki` in compound_eval/replicate, `_JUDGE_MAX_ATTEMPTS=3` retry in judge_run (fixes trial-voiding at source, preserves paired alignment), new `bench/wikigen.py` opus digest generator. Enables raw-pack vs distilled-wiki head-to-head; 664 tests @ 92% | 2026-06-15 | 5f189d2 | [260615-d4p-wiki-arm-distilled-cag-in-bench-judge-re](./quick/260615-d4p-wiki-arm-distilled-cag-in-bench-judge-re/) |

## Session Continuity

Last session: 2026-06-09T14:41:25.275Z
Stopped at: Completed 08-01-PLAN.md — VerifyResult + checker registry + run_verify; 19 tests at 92% coverage
Resume file: None
Next step: `/gsd:plan-phase 6`

## Operator Next Steps

- Start the next milestone with /gsd-new-milestone
