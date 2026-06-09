# Phase 8: Runnable Verification - Context

**Gathered:** 2026-06-08
**Status:** Ready for planning
**Source:** Milestone v0.5.0 plan (VER-01/02) + fixture-schema & doctor-analog exploration (autonomous smart-discuss)

<domain>
## Phase Boundary

Final phase of v0.5.0 "Compounding Loop." Goal: `flowstate verify` turns eval-fixture
`acceptance_gates`/`forbidden_actions` (`.planning/fixtures/`) into **runnable checks** against
produced artifacts, and **closes the loop** — a failed gate feeds the Phase-7 gotchas
accumulator AND appends a Phase-6 run-journal entry, so the next run sees the failure as durable
context. Pure-Python, NO LLM. Depends on Phase 6 (journal) and Phase 7 (gotchas).

**Central design tension (LOCKED resolution):** the fixture gates are free-text natural-language
strings (e.g. "All described functionality works as specified in PROJECT.md") that pure-Python
cannot semantically evaluate. The honest model is a **bounded checker registry**: real mechanical
checks for the checkable subset, explicit SKIP (with reason) for the rest, FAIL only on a real
mechanical failure. No fake LLM-style judgments.
</domain>

<decisions>
## Implementation Decisions (LOCKED)

### VER-01 — `flowstate verify` runnable checks (bounded checker registry)
- New module `flowstate/verify.py`. Pure-Python (stdlib + flowstate.state/context_prefix only;
  NO flowstate.bridge import, NO LLM). Result model: `VerifyResult(gate: str, status:
  Literal["pass","fail","skip"], message: str, fixture: str)` (mirrors doctor's `Diagnosis` shape,
  doctor.py:26-31).
- `run_verify(state, root) -> list[VerifyResult]` reads **every** fixture under
  `.planning/fixtures/*.json` (glob, NOT just starter.json — `_FIXTURE_PATH` is
  context_prefix.py:51), extracts `acceptance_gates` + `forbidden_actions`, runs the registry.
- **Two real mechanical checks:**
  1. **Produced-artifact integrity (backbone — always runs once per verify):** every artifact in
     `state.install_manifest` (state.py InstallEntry: path/checksum) exists on disk and is
     non-empty. A missing/empty produced artifact → FAIL. memory.db (checksum=None) excluded.
  2. **Coverage-threshold gate:** match `acceptance_gates` against a regex like
     `coverage meets or exceeds (\d+)%`; if matched, compare N against a coverage report
     (`coverage.xml` line-rate, else `.coverage`); report present + below N → FAIL; report present
     + meets → PASS; **no report → SKIP** (reason "no coverage report found"). Do NOT run pytest.
- **Everything else SKIPs** with a clear reason ("manual / not mechanically verifiable"): generic
  functional gates, "Milestone satisfied: X" gates, and all `forbidden_actions` (none are
  mechanically checkable this phase). SKIP never fails the run.
- ReDoS-safe, bounded regex; never hangs on adversarial fixture text.

### VER-01 — report, exit, robustness (success criteria #2, #4)
- New `flowstate verify` `@main.command()` in cli.py, doctor-style: Rich report grouping
  PASS/FAIL/SKIP with a summary line (mirror the `doctor` command, cli.py:783-845).
- **Exit code = count of FAIL results** (`sys.exit(fails)` when >0) so it composes in CI /
  pre-commit alongside `flowstate doctor`. SKIPs and PASSes → exit 0.
- **`.planning/fixtures/` absent or empty → exit 0** with a clear "no fixtures to verify" message.
- **Malformed fixture JSON → skip that fixture with a warning, NEVER raise** (try/except per
  fixture file). The whole command is self-contained never-raises (Phase-6 WR-01 discipline).

### VER-02 — close the loop (gotchas + journal)
- For each **FAIL** result: `gotchas.capture_gotcha(memory, source="verify", message=<gate
  failure>, root=root, severity="error")` — deduped by signature, mirrored to GOTCHAS.md (Phase 7).
- **Every** verify run appends ONE run-journal entry via a NEW thin helper
  `journal.append_verify_entry(memory, root, results, *, timestamp=None)` — writes a
  `MemoryKind.RUN` entry tagged `["verify"]` with metadata `{verify: True, gates_passed,
  gates_failed, gates_skipped, failed_signatures}` + an append-only `.planning/RUNLOG.md` line, so
  `flowstate journal` and the `## Since Last Run` prefix layer naturally surface verify runs.
  - Distinct from `append_run_entry` (journal.py:18, which needs pipeline step/manifest state and
    computes artifact deltas) — `append_verify_entry` is a lightweight sibling for standalone
    verify runs. Self-contained never-raises.
  - Journal entry written on every run (the run happened); gotchas captured only on failure (no
    noise on success).
- Net loop: `flowstate verify` fails a gate → gotcha + journal entry persist to memory.db →
  next `flowstate run` injects them via the `## Gotchas` and `## Since Last Run` prefix layers.

### Scope / config
- **Standalone command only** this phase — verify is NOT auto-run at pipeline end (composable in
  CI/pre-commit by the user, like doctor). `--root` option like doctor.
- **No required new config.** Coverage thresholds come from the fixture gate text. Optional: a
  default coverage-report search (`coverage.xml`, then `.coverage`) — no config key needed.
- NO new runtime deps. coverage.xml parsed via stdlib `xml.etree.ElementTree` (already stdlib).
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Verify core (VER-01)
- `flowstate/doctor.py` — `Diagnosis` (L26-31) is the result-shape analog for `VerifyResult`;
  `run_doctor()` (L197-223) is the structure analog for `run_verify()`.
- `flowstate/cli.py` — the `doctor` command (L783-845): Rich table, severity grouping,
  `sys.exit(errors)` exit-code idiom, and the best-effort gotcha-capture block (L809-821) — verify
  clones this structure (report + exit + capture). `resolve_root` + `_root_was_explicit()`.
- `flowstate/context.py` — `generate_starter_fixture()` (L144-223): the fixture schema verify
  consumes (`acceptance_gates`/`forbidden_actions` are `list[str]`; coverage gate text is
  `"Test coverage meets or exceeds {N}% as required."`, L189).
- `flowstate/context_prefix.py` — `_FIXTURE_PATH = ".planning/fixtures/starter.json"` (L51); verify
  globs `.planning/fixtures/*.json`.
- `flowstate/state.py` — `FlowStateModel.install_manifest` + `InstallEntry` (path/owner/kind/
  checksum) — the produced-artifact list for the integrity check. `load_state(root)`.

### Loop wiring (VER-02)
- `flowstate/gotchas.py` — `capture_gotcha(memory, *, source, message, root, severity=...)` (Phase
  7): call with `source="verify"` per FAIL. Self-contained never-raises already.
- `flowstate/journal.py` — `append_run_entry` (L18-26) is the sibling pattern for the NEW
  `append_verify_entry`; reuse the RUNLOG append idiom + `MemoryKind.RUN` + idempotency/never-raise
  discipline. `MemoryEntry.create` for the tagged entry.
- `flowstate/memory.py` — `MemoryStore` open/close, `add`, `count`, `get_by_kind`.

### Tests (analogs)
- `tests/test_cli.py` — `doctor`/`gotchas`/`journal` CLI tests (CliRunner, exit-code asserts,
  tmp_path fixtures) — add `flowstate verify` cases.
- `tests/test_verify.py` (NEW) — registry checks (artifact-integrity FAIL on missing/empty
  artifact; coverage gate PASS/FAIL/SKIP; NL gates SKIP; malformed fixture never raises; no-fixtures
  exit 0).
- `tests/test_journal.py` — extend for `append_verify_entry` (RUN entry tagged verify; RUNLOG line;
  never raises).
- `tests/test_gotchas.py` / `tests/test_cli.py` — verify-fail → gotcha captured (source="verify").

### Fixtures for tests
- Use `generate_starter_fixture()` output (context.py) to build realistic fixtures in tests; write
  to a tmp `.planning/fixtures/` with `install_manifest` entries to exercise the integrity check.
</canonical_refs>

<specifics>
## Specific Ideas

- **Honesty over theater:** SKIP is a first-class status with a human-readable reason; do NOT
  silently pass un-checkable gates and do NOT fabricate semantic verdicts. The report must make the
  checked-vs-skipped split obvious so the user trusts the FAILs.
- **Backbone check earns verify its keep:** even when every gate string is NL/skipped, the
  produced-artifact integrity check is a real, valuable mechanical gate (catches a truncated or
  missing PROJECT.md/ROADMAP.md). Ensure it runs once per verify regardless of gate text.
- **never-raises everywhere** (Phase-6 WR-01 discipline): `run_verify`, the coverage parser, the
  per-fixture loader, `append_verify_entry`, and the CLI all degrade gracefully. A malformed
  fixture, missing coverage.xml, or SQLite hiccup must never traceback — they SKIP or no-op.
- **Coverage parsing:** `coverage.xml` (Cobertura) `line-rate` attr × 100 vs N; `.coverage` is a
  SQLite/binary file — if only `.coverage` exists without `coverage.xml`, SKIP (don't shell out to
  `coverage report`). Keep it pure stdlib.
- **Exit-code contract:** exactly mirror doctor — `sys.exit(count_of_fails)`; 0 when no fails. CI
  treats any non-zero as failure.
- Constraints: ruff line-length 100 + double quotes + snake_case, `from __future__ import
  annotations`, coverage ≥80% (pre-commit on push), no new runtime deps, state migration
  v0.1→0.2→0.3 unaffected.
</specifics>

<deferred>
## Deferred Ideas
- Auto-running `flowstate verify` at the end of `run_pipeline` → out of scope (standalone command
  this phase; user wires it into CI/pre-commit). A future milestone could add an opt-in
  `verify_after_run` config.
- LLM-assisted semantic gate evaluation (judging NL gates) → explicitly OUT (milestone constraint:
  pure-Python, no LLM). SKIP is the correct answer for NL gates.
- Mechanical `forbidden_actions` enforcement (e.g. dependency-diff for "no new deps") → deferred;
  no baseline exists to diff against this phase.
</deferred>

---

*Phase: 08-runnable-verification*
*Context gathered: 2026-06-08 via milestone v0.5.0 plan + fixture-schema/doctor-analog exploration (autonomous smart-discuss)*
