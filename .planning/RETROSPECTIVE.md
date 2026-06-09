# Project Retrospective

*A living document updated after each milestone. Lessons feed forward into future planning.*

## Milestone: v0.3.0 — v2 Pivot + Operate-Safely

**Shipped:** 2026-06-06
**Phases:** 2 (Phase 1 direct commits, Phase 2 four GSD plans) | **Plans:** 4 | **Quick tasks:** 2

### What Was Built
- **v2 pivot landed** — `config.py` default-root resolution (`--root` > saved config > cwd) wired across the CLI, FTS5 query sanitization, built-in tool markers, version bumped to 0.3.0.
- **Install manifest** — `FlowStateModel.install_manifest` records every file `init` writes (path/owner/kind/created_at/checksum); `fresh` consults it and reports orphans instead of blind-deleting.
- **doctor / repair** — 6 pure-Python health checks with exit-code = error count; `repair` applies the safe subset by default, gates destructive fixes behind `--apply-destructive`.
- **status --markdown** — 3-section markdown handoff doc (tools table, active phase, memory stats) with optional `--write`.
- **Hook env-gating** — `FLOWSTATE_HANDLERS` profiles (minimal/standard/strict) + `FLOWSTATE_DISABLED_HANDLERS` denylist with precedence.

### What Worked
- **Coarse granularity (2 phases) for a single maintainer** — kept diffs reviewable and avoided coordination overhead; both phases shipped clean.
- **Land the pivot before adding new surface** — committing the ~370 lines of unstaged v2 work first kept the bug surface unambiguous for the operate-safely features built on top.
- **Borrowing proven ECC patterns** (install manifest, doctor/repair, env-var hook profiles) rather than inventing — and explicitly *rejecting* ECC's surface-area-explosion patterns (7-harness packaging, Rust rewrite, 50KB hooks.json).

### What Was Inefficient
- **Milestone left in `verifying` limbo** — work shipped 2026-05-25 but `complete-milestone` wasn't run until 2026-06-06; STATE.md frontmatter stayed stale and the audit later flagged completed quick tasks as "open" (false positives from missing `status:` frontmatter).
- **REQUIREMENTS.md checkboxes never ticked** for the PIVOT block even though the traceability table and PROJECT.md marked them validated — a small consistency drift.

### Patterns Established
- **Safe-by-default destructive operations** — anything that deletes (orphans, memory rows, corrupt-db recreation) requires an explicit `--apply-destructive` flag.
- **Pydantic-immutable-safe updates** via `entry.model_copy(update={...})` + rebuilt list, never in-place attribute assignment.
- **Pure functions for renderers** — status renderer takes (state, root) → str and never raises on missing files (graceful fallback for absent memory.db / ROADMAP.md).
- **Per-call env-var lookup over module-level cache** for handler gating — trivially monkeypatchable, no stale state.

### Key Lessons
1. **Run `complete-milestone` at ship time, not weeks later** — the stale-frontmatter gap (Bug #2630 territory) and false-positive audits both trace to deferring the close.
2. **Add a `status:` field to quick-task SUMMARY frontmatter** so the open-artifact audit doesn't read shipped work as "missing."
3. **Borrow patterns, reject surface area** — the discipline of explicitly listing what *not* to take from a reference project (ECC) kept scope bounded.

### Cost Observations
- Model mix: predominantly opus for planning/execution.
- Notable: confirmed `claude --print` server-side prompt cache fires across back-to-back subprocesses (−32% wall, −37% API on call 2) — relevant to future bridge-cost optimization.

---

## Milestone: v0.4.0 — Context Compaction & Compounding

**Shipped:** 2026-06-06
**Phases:** 3 (Ingredients → Integration → UX) | **Plans:** 6 | **Tasks:** 13

### What Was Built
- Repomix pack ingredient: `flowstate pack` (CLI locator + staleness repack), `.mcp.json` + `mcp__repomix` retrieval-on-top.
- Karpathy `CANON` as the always-on, suppressible bridge system-prompt layer.
- ECC-modeled eval fixtures scaffolded + manifest-tracked.
- `build_context_prefix()` — fixtures → pack(if-fits) → memory, one build per run, fit→compress→omit ladder, `ENABLE_PROMPT_CACHING_1H` lean-in.
- Scaffold-only `flowstate kickoff` (no LLM) + enhanced shared interview (validation + branching).
- `status:` SUMMARY frontmatter standardization + backfill.

### What Worked
- **Closing v0.3 at the start of the session** (the lesson from last retro) meant v0.4 began from clean, trustworthy state — no stale-frontmatter drift this time.
- **Rich CONTEXT.md per phase, authored from the milestone plan + exploration**, gave planners high-signal input without a research pass (research was disabled) — plans came back implementation-ready.
- **The plan-checker earned its cost three times:** caught a real `_migrate_state` v0.3→v0.4 early-exit guard bug, a ROADMAP success-criterion that would have falsely failed Phase 4 verification (canon-in-prefix), and committed repo pollution (`scripts/_dx01_verify.py`) — all before execution.
- **Sequential-on-main execution** (over parallel worktrees) was the right call for an unattended autonomous chain on `main` — zero merge hazards, every commit gated by pre-commit pytest.

### What Was Inefficient
- The SDK `milestone.complete` accomplishment-extraction produced empty `One-liner:` placeholders and a wrong task count — required a manual MILESTONES.md rewrite (same gap as v0.3, now a known quantity).
- DX-01 hit a real SDK quirk: `audit-open` only reads bare `SUMMARY.md`, not `{id}-SUMMARY.md`, forcing dual anchor files in the quick-task dirs — functional but slightly awkward; worth a future SDK fix or convention change.

### Patterns Established
- **CAG = prefix-cache-optimized layering**, not literal KV preload — the honest framing for `claude --print`.
- **Two canon channels kept separate:** system-prompt canon (bridge) vs. user-prompt context prefix — never duplicate.
- **External tools (repomix) located like `claude`** (PATH / env var), graceful when absent — keeps the no-new-Python-deps rule intact.
- **One `run_interview` shared by `init` and `kickoff`** — single source of truth for the intake flow.

### Key Lessons
1. Author per-phase CONTEXT.md from the milestone plan when running research-disabled autonomy — it's the planner's whole world.
2. When a ROADMAP success criterion and a locked CONTEXT decision disagree, fix the ROADMAP before execution — the post-hoc verifier treats SC text as ground truth.
3. The SDK accomplishment extractor is unreliable; plan to rewrite the MILESTONES entry by hand.

### Cost Observations
- Model mix: opus for planning/orchestration, sonnet for executors/checkers/verifiers.
- Full autonomous chain (close v0.3 → new-milestone → plan+execute+verify 3 phases → close v0.4) ran in one session; 381 tests at 92.85% throughout.

---

## Milestone: v0.5.0 — Compounding Loop

**Shipped:** 2026-06-09
**Phases:** 3 (Run Journal → Gotchas Accumulator → Runnable Verification) | **Plans:** 10 | **Tasks:** 18

### What Was Built
- Run journal: `journal.append_run_entry` writes one append-only, delta-only `MemoryKind.RUN` entry per pipeline run (checksum-snapshot diff, idempotent, never-raises), mirrored to `.planning/RUNLOG.md`; `## Since Last Run` prefix layer + `flowstate journal` viewer.
- Gotchas accumulator: `gotchas.py` captures four bounded structured sources (doctor/repair, executor failures, harvested VERIFICATION.md/REVIEW.md) into signature-deduped, capped `MemoryKind.INSIGHT` gotchas; `## Gotchas` layer before memory; `MemoryStore.update`/`delete`/`get_gotchas`; `flowstate gotchas` list/prune + `.planning/GOTCHAS.md` mirror.
- Runnable verification: `flowstate verify` bounded checker registry (artifact-integrity backbone + coverage gate, honest SKIP for NL gates), CI-composable exit code, never-raises; failures feed gotchas + `append_verify_entry` — the loop closes.

### What Worked
- **The "honest SKIP" framing for verify** turned an unbuildable requirement ("check that all functionality works" with no LLM) into a shippable, trustworthy one — real checks for the checkable subset, explicit SKIP with reasons for the rest.
- **Adversarial code-review→fix pass after every phase** caught four real bugs that verification missed: a CR-01 budget-participation gap (the new layer bypassed the fit-ladder), a CR-02 repair/doctor dedup-source mislabel, a Z-suffix-timestamp normalization miss, and a 500-entry dedup-scan scaling bug. The reviewer is a distinct, load-bearing gate from the verifier.
- **Phase-6 review lessons propagated forward as explicit CONTEXT/planner constraints** (CR-01 budget participation, WR-01 self-contained never-raises) — Phase 7 and 8 plans baked them in, so the same class of bug was pre-empted at plan time.
- **Per-phase smart-discuss grounded in a fresh codebase surface-map** (especially Phase 7's "which of the four sources actually exist in-runtime") kept proposals honest and prevented planning against imagined APIs.

### What Was Inefficient
- An executor died mid-plan from an API socket error (08-01); recovery required a filesystem/git spot-check + a scoped resume executor to finish Task 2. The sequential-on-main model made recovery clean (Task 1's commit was intact), but it cost a round-trip.
- The SDK `milestone.complete` accomplishment extractor produced empty `One-liner:` placeholders again (third milestone running) — manual MILESTONES.md rewrite still required. This is now a reliable tax, not a surprise.

### Patterns Established
- **Five-layer prefix, most-stable-first:** fixtures → pack → gotchas → memory → since-last-run; every layer participates in the budget fit-ladder + final guard (no silent cache-window blowout).
- **Pure-Python compounding substrate:** journal/gotchas/verify do zero LLM/bridge calls and only consume STRUCTURED outputs — deterministic, cheap, inspectable; no transcript mining.
- **Signature dedup for failure signals:** normalize (paths/line-numbers/timestamps/run_ids → placeholders) → sha256 → upsert last-seen/count, so a recurring failure is one growing entry, not N.

### Key Lessons
1. When a requirement names a capability the runtime can't honestly deliver (semantic gate eval without an LLM), redefine it as a bounded mechanical check + explicit SKIP rather than faking it — and surface that decision in smart-discuss.
2. Carry each phase's review findings forward as the next phase's planning constraints; the cheapest place to fix a recurring bug class is the plan, not the diff.
3. On an unattended chain, verify executor completion from git/filesystem after any transport error before retrying — partial atomic commits are resumable; blind retries are not.

### Cost Observations
- Model mix: opus for orchestration/planning, sonnet for executors/checkers/verifiers/reviewers/fixers.
- Full autonomous chain (smart-discuss → plan → plan-check → execute → verify → review → fix → complete, ×3 phases, then milestone close) ran across one session; suite grew 381 → 549 tests, coverage held ~92.2% throughout.
- One executor socket-error recovery; one Bash classifier-unavailable transient — both absorbed without losing work.

---

## Cross-Milestone Trends

### Process Evolution

| Milestone | Phases | Key Change |
|-----------|--------|------------|
| v0.3.0 | 2 | Adopted GSD for Phase 2; coarse granularity for solo maintainer |
| v0.4.0 | 3 | Full autonomous chain (new-milestone → plan → execute → verify → complete); plan-checker as a load-bearing gate |
| v0.5.0 | 3 | Added code-review→fix as a per-phase gate distinct from verification; review findings carried forward as next-phase planning constraints |

### Cumulative Quality

| Milestone | Coverage | Zero-Dep Additions |
|-----------|----------|-------------------|
| v0.3.0 | ≥80% (enforced) | doctor, repair, status --markdown, hook gating — all pure-Python, no new runtime deps |
| v0.4.0 | 92.85% | pack, CANON, fixtures, build_context_prefix, kickoff — repomix is external (Node CLI/MCP), still zero new Python deps |
| v0.5.0 | 92.25% | journal, gotchas, verify + `flowstate journal`/`gotchas`/`verify` commands — pure-Python (stdlib hashlib/re/xml.etree), zero new Python deps, zero bridge imports |

### Top Lessons (Verified Across Milestones)

1. Close milestones at ship time to keep state and audits trustworthy. (v0.3 missed it; v0.4 confirmed the payoff.)
2. Safe-by-default for any destructive CLI operation.
3. The plan-checker pays for itself — adversarial pre-execution review catches real bugs (migration guards, success-criteria errors, repo pollution).
4. The SDK accomplishment extractor needs a manual pass at milestone close.
