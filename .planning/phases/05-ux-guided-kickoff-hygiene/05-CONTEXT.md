# Phase 5: UX — Guided Kickoff + Hygiene - Context

**Gathered:** 2026-06-06
**Status:** Ready for planning
**Source:** Milestone v0.4.0 plan + Phases 3-4 outcomes + codebase exploration (auto mode)

<domain>
## Phase Boundary

The final v0.4.0 phase: a fast scaffold-only project kickoff and the SUMMARY `status:`
hygiene fix. In scope: `flowstate kickoff` command (KICK-01), enhanced shared interview
(KICK-02), `status:` SUMMARY frontmatter standardization + backfill (DX-01). This phase
CONSUMES what Phases 3-4 built (pack, fixtures, context_prefix) — it does not build new
context machinery.
</domain>

<decisions>
## Implementation Decisions (LOCKED)

### KICK-01 — scaffold-only kickoff command
- New `flowstate kickoff` Click command (cli.py). Flow: load/create state → `run_interview()`
  → `write_context_files()` (already scaffolds PROJECT/ROADMAP/CLAUDE.md/config/fixture/.mcp.json
  from Phase 3) → `run_pack()` (Phase 3) → save state. **NO `run_pipeline()`, NO bridge/LLM call.**
- Contrast with `flowstate init`, which runs the full 5-step LLM pipeline after the interview.
  kickoff is the "scaffold and stop" entry point.
- Options mirror init where sensible (`--root`, `--skip-interview`), minus pipeline flags
  (`--model`/`--budget`/`--effort` are pipeline concerns — omit them).

### KICK-02 — enhanced shared interview
- Enhance `run_interview()` in interview.py (branching and/or validation on the existing
  sections: research/strategy/management/discipline). Any new fields persist to
  `state.interview` (InterviewAnswers in state.py).
- **Single source of truth:** both `flowstate init` and `flowstate kickoff` call the SAME
  `run_interview()` — the new questions appear in BOTH with no divergence. Do not fork the
  interview.

### DX-01 — status: SUMMARY frontmatter
- Standardize a `status:` frontmatter field with allowed values: complete / verified / blocked /
  paused / drafted.
- **Backfill the 2 existing quick-task summaries (the audit false-positive fix):**
  - `.planning/quick/260525-m9v-.../260525-m9v-SUMMARY.md` — HAS yaml frontmatter; add `status: complete`.
  - `.planning/quick/260525-o6h-.../260525-o6h-SUMMARY.md` — has NO frontmatter (starts with `# 260525-o6h — SUMMARY`); prepend a minimal yaml block with at least `status: complete` (+ phase/plan if cheap).
- After backfill, `gsd-sdk query audit-open` must NOT flag these two as "missing"/in-flight.
- Document the convention (e.g. a short note in CLAUDE.md or a GSD reference) so future
  quick-task summaries include `status:`. There is no official GSD quick-task frontmatter template
  — this establishes the local convention.
- This is a docs/hygiene change — no Python source touched for DX-01.
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Kickoff command + interview
- `flowstate/cli.py` — the `init` command (~L69-104) is the analog; `kickoff` mirrors its
  interview + scaffold steps but omits `run_pipeline()`. Click group structure + `--root`
  resolution via `config.resolve_root`.
- `flowstate/interview.py` — `run_interview()` (~L60-112) + section definitions (~L13-57).
- `flowstate/state.py` — `InterviewAnswers` (~L28-34) for any new fields.
- `flowstate/context.py` — `write_context_files()` (already scaffolds fixture + .mcp.json, Phase 3).
- `flowstate/pack.py` — `run_pack()` (Phase 3) for the scaffold pack.

### Hygiene targets (DX-01)
- `.planning/quick/260525-m9v-unify-memory-injection-at-orchestrator-b/260525-m9v-SUMMARY.md` (has frontmatter)
- `.planning/quick/260525-o6h-spike-confirm-claude-print-server-side-p/260525-o6h-SUMMARY.md` (NO frontmatter)
- `gsd-sdk query audit-open` (the audit that currently false-flags them).

### Tests (analogs)
- `tests/test_cli.py` — CliRunner + `healthy_install` fixture (test the new `kickoff` command;
  assert NO pipeline/bridge invocation — e.g. monkeypatch run_pipeline and assert not called).
- `tests/test_interview.py` — interview question/field tests.
- `tests/test_context.py` — scaffold output.
</canonical_refs>

<specifics>
## Specific Ideas

- The cleanest KICK-01 test: `CliRunner` invoke `kickoff` with `--skip-interview`, monkeypatch
  `orchestrator.run_pipeline` and assert it is NEVER called; assert context files + pack scaffolded.
- KICK-02 test: assert the new interview field(s) exist on InterviewAnswers and that `run_interview`
  collects them (drive prompts via CliRunner input or monkeypatch rich prompts as test_interview.py does).
- DX-01: keep the o6h frontmatter prepend minimal and valid YAML; don't rewrite the body.
- Constraints: ruff line-length 100 + double quotes, snake_case, NO new Python runtime deps,
  coverage ≥80% (pre-commit enforces). repomix not on PATH (npx available) — kickoff's pack step
  must degrade gracefully (Phase 3 already handles this); kickoff tests monkeypatch run_pack.
</specifics>

<deferred>
## Deferred Ideas
- None — this is the last phase of v0.4.0. (v2 backlog: DIST/XHARN/EVAL remain for a future milestone.)
</deferred>

---

*Phase: 05-ux-guided-kickoff-hygiene*
*Context gathered: 2026-06-06 via milestone plan + Phases 3-4 outcomes (auto mode)*
