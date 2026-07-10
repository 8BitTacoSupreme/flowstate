---
phase: 14-vendor-surface
plan: 02
subsystem: docs
status: complete
tags: [readme, vend-05, reconciliation, acknowledgments]
requires: [VEND-05]
provides: ["README claims match v0.6.1 code", "REQUIREMENTS test-count aligned"]
affects: [README.md, .planning/REQUIREMENTS.md]
tech-stack:
  added: []
  patterns: ["docs-as-code reconciliation against shipped mechanisms"]
key-files:
  created: []
  modified:
    - README.md
    - .planning/REQUIREMENTS.md
decisions:
  - "Test count set to 985 (live pytest --collect-only), the current-true value; 14-04 re-derives post-phase"
metrics:
  duration: ~6 min
  completed: 2026-07-10
requirements: [VEND-05]
---

# Phase 14 Plan 02: README Reconciliation (VEND-05) Summary

Reconciled every remaining VEND-05 README claim to the shipped v0.6.1 code: fixed the Superpowers upstream URL, corrected the `doctor` check count to the real 6, clarified sqlite-vec-is-core vs fastembed-is-optional, confirmed the self-reconciling test count (985), and rewrote the three adapter acknowledgments to describe what Phase 13 actually built — with REQUIREMENTS.md brought into agreement.

## What Shipped

**Task 1 — factual claims (commit 55ed6ba):**
- Superpowers acknowledgment URL `obra/claude-code-superpowers` (404) → `obra/superpowers`.
- `flowstate doctor` capabilities line now lists all **6** registered checks (manifest integrity, memory schema, root resolution, claude CLI, `stale_status`, orphan files) — matching `run_doctor` in `flowstate/doctor.py`.
- sqlite-vec/fastembed acknowledgment reworded: `sqlite-vec` is a **core** dependency (base deps in `pyproject.toml`), only `fastembed` sits behind the `[semantic]` extra. Prior wording implied both were optional.
- Test count: verified live `uv run --frozen python -m pytest --collect-only -q` reports **985 tests**. README line already carried 985 (from prior commit 845f648); confirmed it equals the collected count and is neither 803 nor 947 — no change needed to the literal.
- `.planning/REQUIREMENTS.md` VEND-05: stale `803 → 947` replaced with a reference to the real collect-only count (985 at Wave 1; re-derived in 14-04).

**Task 2 — adapter acknowledgments to Phase 13 reality (commit 54b40b3):**
- **Autoresearch** (research adapter): now describes measure→keep/discard groundedness scoring over output — sections scored vs the fixture's `retrieval_questions`, bounded retry, discard-if-weak, kept/discarded counts recorded, fail-loud when all discarded. Matches `flowstate/tools/research.py`.
- **Gstack** (strategy adapter): now describes the five 0–10 dimension scored rubric + `ship`/`pivot`/`kill` verdict, with an unparseable rubric treated as a failure. Matches `flowstate/tools/strategy.py`.
- **Superpowers** (discipline adapter): rewritten (in the Task 1 commit alongside the URL fix, since both touched one line) to describe running the project's tests as a gating check, reading real git state (dirty / branch / ahead-behind), inspecting hook contents, and failing the pipeline. Matches `flowstate/discipline.py`.

No acknowledgment describes an unbuilt mechanism.

## Deviations from Plan

The Superpowers bullet's prose rewrite (a Task 2 concern) was applied in the Task 1 commit because the URL fix (Task 1) and prose rewrite (Task 2) targeted the same single Markdown line — splitting them into two edits of the same line would have been artificial. Both tasks' acceptance criteria for that bullet are satisfied. Tracked as `[Rule 3 - blocking] shared-line edit consolidation`; no behavioral impact.

## Verification

- Task 1 automated gate: `985 tests` present, `obra/superpowers` present, `obra/claude-code-superpowers` absent, `stale_status` present, no `803`/`947` in README, no `803 → 947` in REQUIREMENTS → **OK**.
- Task 2 automated gate: `keep/discard`, `ship/pivot/kill`, `git state`/`hook contents` all present; no `draws on the idea` / `implements a similar` remaining → **OK**.
- Pre-commit hooks passed on both commits (ruff, EOF, whitespace, large-file, merge-conflict, debug-statement).

## Threat Flags

None. T-14-04 (dead/typosquattable Superpowers URL) and T-14-05 (unbuilt-mechanism claims) are both mitigated; T-14-06 (dep-optionality/count wording) is docs-only, no runtime effect.

## Self-Check: PASSED

- README.md modified and committed (54b40b3, 55ed6ba) — FOUND
- .planning/REQUIREMENTS.md modified and committed (55ed6ba) — FOUND
- Commits 55ed6ba and 54b40b3 present in git log — FOUND
