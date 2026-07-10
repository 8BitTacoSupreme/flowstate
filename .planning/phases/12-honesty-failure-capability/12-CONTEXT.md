# Phase 12: Honesty & Failure-Capability - Context

**Gathered:** 2026-07-10
**Status:** Ready for planning
**Source:** Direct stub inventory (agent-verified file:line, then re-verified against current code this session)

<domain>
## Phase Boundary

Make the FlowState pipeline **incapable of reporting a broken run as clean**. Today three
paths report success on failure. This phase makes failure representable and surfaced — it is
the honesty foundation Phase 13 builds on (an adapter can't report a mechanism *running* until
it can report one *failing*). **No new adapter mechanisms in this phase** — those are Phase 13.
Scope is exactly HON-01..06.

Requirements: HON-01, HON-02, HON-03, HON-04, HON-05, HON-06.
</domain>

<decisions>
## Implementation Decisions

### Verified current state (re-checked this session — trust these over any summary)
- **`flowstate/discipline.py:44-59`** — `check_setup()` computes `passed`/`total` for the summary
  string only, then hardcodes `AuditResult(success=True, ...)` (`:56`). `success=False` is never
  constructed. `AuditResult` (`:12-16`) already carries `checks: dict[str,bool]` and `summary`.
- **`flowstate/orchestrator.py:317-319`** — the Discipline step **bypasses the generic `_run_step`
  runner**: it calls `check_setup(root)` then `update_tool(state, "discipline", COMPLETED)`
  unconditionally and prints `audit.summary` in green. `audit.success`/`.checks` are never read.
- **`flowstate/orchestrator.py:119-164`** — the generic `_run_step` runner **already does the right
  thing**: on `result.success` → `COMPLETED` + `StepCompleted`; else → `ToolStatus.BLOCKED` +
  `StepFailed` + red output. Research, strategy, and gsd all flow through `_run_step` via
  `execute_fn`. So HON-03/HON-04 are "make `execute()` return `success=False`" — the runner
  handles the rest.
- **`flowstate/orchestrator.py:340-350`** — `_print_summary` already reports `blocked` count and
  prints the non-green "N blocked" line when `blocked > 0`. Once a step is BLOCKED, the summary is
  already correct. HON-02's "summary reflects it" is satisfied by existing code once Discipline can
  be BLOCKED.
- **`flowstate/orchestrator.py:171-173`** — live-run guard: `if not dry_run and not bridge.available:`
  swaps `bridge = ClaudeBridge(config=..., dry_run=True)`. The adapters are still constructed with
  the OUTER `dry_run` (False), so they take the LIVE path but call a stub bridge that returns
  `[dry-run] claude prompt (N chars): ...` (`bridge.py:212-215`), which the adapters write to
  `report.md`/`strategy.md` and report as success.
- **`flowstate/tools/research.py:100-122`** — `for/else` appends "*Research failed*" per exhausted
  topic, then unconditionally `return ToolResult(success=True, ...)`. No `success=False` path.
- **`flowstate/tools/strategy.py`** — single bridge call; writes output (or empty/failed) and
  reports success. (Confirm the exact return during planning.)
- **`flowstate/tools/gsd_adapter.py:8`** — module docstring promises "file generation, with optional
  LLM enrichment"; the code only calls `write_context_files`. No bridge call.

### HON-01 — discipline can fail
- `check_setup()` derives `success` from a **required-set**, not literal `True`. Required-set
  (minimum for a "healthy enough to proceed" verdict): **`git_repo` AND `pytest_config`**. If either
  required check is False → `success=False`. The other five checks remain informational (reported,
  not required). Keep the `checks` dict and `summary` exactly as-is; only `success` changes.
- Rationale: git + a test config are the floor for a project FlowState is scaffolding discipline
  onto; hooks/tests-dir/src-dir/planning-dir are advisory. Keep the required-set small and explicit.

### HON-02 — orchestrator surfaces the audit; `flowstate discipline` CLI
- The Discipline step must go through the same success→COMPLETED / failure→BLOCKED + event path as
  every other step. Preferred: **route it through `_run_step`** by wrapping `check_setup` in a tiny
  `execute_fn` that returns a `ToolResult(success=audit.success, output=audit.summary, error=<failed
  checks> if not success)`. This reuses the existing BLOCKED + `StepFailed` machinery and the
  `_print_summary` blocked-count path — no new summary logic.
- Add a `flowstate discipline` CLI subcommand (mirror `flowstate verify`'s shape at
  `cli.py` — it runs `check_setup`, prints the summary, and `sys.exit(0)` on success / non-zero on
  failure). CI-composable, like `doctor`/`verify`.

### HON-03 — research surfaces failure
- `research.execute()` returns `ToolResult(success=False, error=...)` when **every** topic exhausts
  its attempts (zero sections produced). Partial success (≥1 topic produced output) stays
  `success=True` but the report still notes the failed topics. The "*Research failed*" notice must
  never coexist with an all-failed `success=True`.

### HON-04 — strategy surfaces failure
- `strategy.execute()` returns `ToolResult(success=False)` when its bridge call fails or returns
  empty, instead of writing a failed/empty `strategy.md` and reporting success.

### HON-05 — live run with no `claude` CLI fails loud
- Remove the silent swap-to-stub-bridge (`orchestrator.py:171-173`). When `not dry_run and not
  bridge.available`: the deterministic steps (context generation, discipline) may still run, but the
  **bridge-dependent steps (research, strategy) are marked BLOCKED** with a clear error (e.g.
  "claude CLI not found — run `flowstate check`"), and **no `[dry-run]` stub text is written** to
  `report.md`/`strategy.md`. A run missing the CLI must not report "All steps succeeded."
- Do NOT change genuine `--dry-run` behavior (explicit `state.preferences.dry_run=True` still writes
  MOCK_* artifacts and reports success — that's the intended offline/test path).

### HON-06 — reconcile gsd_adapter docstring
- `gsd_adapter.py:8` — drop the "with optional LLM enrichment" claim (the adapter is deterministic
  file generation). One-line docstring fix; do not add an unused bridge path.

### Tests that encode the current lie (planner must account for)
- Any existing test asserting `check_setup(...).success is True` on a bare/failing repo, or asserting
  the Discipline step is always COMPLETED, or that research returns success on all-failed topics,
  encodes the bug and must be updated to the new honest behavior. Search `tests/test_discipline.py`,
  `tests/test_orchestrator.py`, `tests/test_research*.py`, `tests/test_strategy*.py`.
- Coverage gate ≥80% (`pyproject.toml --cov-fail-under=80`). Add tests for each new failure path.
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### The code being changed
- `flowstate/discipline.py` — `check_setup` / `AuditResult` (HON-01)
- `flowstate/orchestrator.py` — `_run_step` (119-164), Discipline step (313-320), live-run guard (166-173), `_print_summary` (340-350) (HON-02, HON-05)
- `flowstate/tools/research.py` — `execute` (69-122) (HON-03)
- `flowstate/tools/strategy.py` — `execute` (HON-04)
- `flowstate/tools/gsd_adapter.py` — module docstring (HON-06)
- `flowstate/cli.py` — add `discipline` subcommand; mirror `verify`'s exit-code shape (HON-02)

### Existing patterns to mirror (reuse, don't reinvent)
- `flowstate/verify.py` + its `cli.py` command — the CI-composable non-zero-exit pattern for the new `flowstate discipline` command
- `_run_step`'s existing success/BLOCKED/event handling — reuse it for Discipline rather than adding parallel logic
- `ToolResult(success, output, artifacts, error)` (`flowstate/tools/base.py`) — the return contract HON-03/04 populate

### Governing decisions
- `.planning/PROJECT.md` Key Decisions — "Adapters must be able to fail (v0.6.1)"; `flowstate verify` SKIPs-not-fakes honesty precedent
- `bench/BENCHMARK_HANDOFF.md` §6 integrity rule: "a run that fails must fail loud"
</canonical_refs>

<specifics>
## Specific Ideas

- Keep the change surgical: `success` derivation + step routing + return-value honesty + a docstring
  fix + one CLI subcommand. No adapter mechanism work (that's Phase 13). No behavior change to genuine
  `--dry-run`.
- The `flowstate discipline` command is the smallest new surface; model it exactly on `flowstate verify`.
</specifics>

<deferred>
## Deferred Ideas

- Real test execution / git-state reading / hook-content checks in discipline → **Phase 13 (MECH-03)**.
- Research measure→keep/discard and strategy scored rubric → **Phase 13 (MECH-01/02)**.
- The dead-surface cleanup (`output_format="json"` callers, `invoke_skill`, wiki caller, pack
  silent-drop logging) → **v0.8.0 / DEAD-F1**.
</deferred>

---

*Phase: 12-honesty-failure-capability*
*Context gathered: 2026-07-10 (direct inventory, re-verified against current code)*
