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

## Cross-Milestone Trends

### Process Evolution

| Milestone | Phases | Key Change |
|-----------|--------|------------|
| v0.3.0 | 2 | Adopted GSD for Phase 2; coarse granularity for solo maintainer |

### Cumulative Quality

| Milestone | Coverage | Zero-Dep Additions |
|-----------|----------|-------------------|
| v0.3.0 | ≥80% (enforced) | doctor, repair, status --markdown, hook gating — all pure-Python, no new runtime deps |

### Top Lessons (Verified Across Milestones)

1. Close milestones at ship time to keep state and audits trustworthy.
2. Safe-by-default for any destructive CLI operation.
