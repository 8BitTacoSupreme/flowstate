---
phase: 13-adapters-earn-their-names
plan: 01
subsystem: tools/research
status: complete
tags: [MECH-01, research-adapter, groundedness, autoresearch]
requires:
  - "flowstate/tools/base.py::ToolAdapter (bridge, prior_knowledge)"
  - "flowstate/bridge.py::BridgeResult"
  - ".planning/fixtures/starter.json::retrieval_questions"
provides:
  - "Groundedness measure->keep/discard loop over research OUTPUT"
  - "_load_retrieval_questions / ResearchAdapter._score_groundedness"
affects:
  - "flowstate/tools/research.py"
tech-stack:
  added: []
  patterns:
    - "measure->keep/discard over OUTPUT (Autoresearch), never over prompts (MECH-01)"
    - "bounded regex parse of untrusted model score text (no dynamic eval)"
key-files:
  created:
    - "tests/test_research_grounding.py"
  modified:
    - "flowstate/tools/research.py"
decisions:
  - "_score_groundedness is a METHOD (needs self.bridge), not a module function — the plan's <verify> hasattr-on-module check is inconsistent with its own <action>; satisfied the authoritative 'contains def _score_groundedness(' criterion instead"
  - "Groundedness threshold 0.6, retry budget 1 (at most one regeneration beyond initial success per section)"
  - "All-discarded run counts as produced==0 -> success=False, preserving Phase 12 HON-03 fail-loud semantics"
metrics:
  duration: ~12 min
  completed: 2026-07-10
  tasks: 2
  files: 2
---

# Phase 13 Plan 01: Research Adapter Groundedness Measure->Keep/Discard Summary

Gave the `research` adapter Autoresearch's core mechanism (MECH-01): after each topic section is generated it is scored for groundedness against the active fixture's `retrieval_questions`, weak sections are regenerated once (same prompt, unmodified) and re-scored, and still-weak sections are discarded — a measurement over OUTPUT that never touches the prompt.

## What Was Built

**Task 1 — `flowstate/tools/research.py`** (commit `c1f1d42`, docstring fix `12dc4de`)
- `_load_retrieval_questions(root)` — reads `.planning/fixtures/starter.json`, `json.loads` in try/except, returns the `retrieval_questions` list or `[]` on any failure (missing file, malformed JSON, wrong type).
- `ResearchAdapter._score_groundedness(section, questions)` — issues ONE scoring bridge call (`model="sonnet"`, `max_turns=2`, `allowed_tools=[]` so the judge cannot browse), asks for a 0-10 integer, parses with a strict bounded regex `re.search(r"-?\d{1,3}")`, clamps to 0-10, returns `score/10.0`. Bridge failure or unparseable output -> `0.0` (weak, not a crash). No dynamic evaluation of model text.
- `ResearchAdapter._generate_section(prompt)` — factored the existing bridge-success retry loop (`_RESEARCH_MAX_ATTEMPTS`) so generation is reused unchanged for the initial call and the groundedness regeneration.
- `execute()` — after a section is generated, when `questions` is non-empty it scores, retries within `_GROUNDEDNESS_MAX_RETRIES=1`, and keeps (`>= _GROUNDEDNESS_THRESHOLD=0.6`) or discards. Records `## Groundedness\n\n- Kept: N sections\n- Discarded: <topics|none>` in the report body and `kept=N discarded=M` in `ToolResult.output`. `produced==0` (all failed or all discarded) -> `success=False`.
- The `if self.dry_run:` branch and `MOCK_REPORT` are byte-identical (no diff lines inside that branch); `_build_topic_prompt` / `_split_topics` untouched.

**Task 2 — `tests/test_research_grounding.py`** (commit `8025c06`)
- Five offline tests: keep-all (score 10), discard-all-weak (score 0 -> `success=False`, topic listed discarded), weak-then-strong retry (asserts regeneration prompt == original prompt and scoring call uses `allowed_tools=[]`), no-fixture skip (no scoring calls, report notes "scoring skipped: no fixture"), and a dry-run golden equal to `MOCK_REPORT.format(...)`.
- Driven by a `MagicMock` bridge with sequenced `side_effect`; fixture written under `tmp_path`. No live `claude` CLI or network.

## Acceptance Criteria

- `research.py` contains `def _load_retrieval_questions(` and `def _score_groundedness(` — met.
- Contains `_GROUNDEDNESS_THRESHOLD` and `_GROUNDEDNESS_MAX_RETRIES` — met.
- `grep -n "eval(\|exec(\|literal_eval" flowstate/tools/research.py` returns nothing — met (docstring reworded in `12dc4de` to avoid a self-inflicted match).
- `if self.dry_run:` / `MOCK_REPORT` byte-identical — met (dry-run golden test locks it).
- Regeneration prompt identical to the original topic prompt — met (asserted in `test_weak_then_strong...`).
- `ruff check` + `ruff format --check` pass — met.
- `python -m pytest tests/test_research_grounding.py tests/test_tools.py -q` exits 0 — met (25 passed).
- Full suite: `959 passed`, coverage `92.18%` (>= 80 floor); `research.py` at 95%.

## Deviations from Plan

**1. [Rule 3 - Blocking] Plan `<verify>` hasattr check is inconsistent with its `<action>`.**
- **Found during:** Task 1 verification.
- **Issue:** The plan's `<automated>` verify runs `hasattr(r, '_score_groundedness')` at module level, but the `<action>` explicitly mandates a *method* `_score_groundedness(self, ...)` (it needs `self.bridge`). A method is never a module attribute, so the literal verify can never pass.
- **Fix:** Implemented the method exactly as the `<action>` requires and satisfied the authoritative acceptance criterion instead (`grep "def _score_groundedness("` present; `hasattr(ResearchAdapter, '_score_groundedness')` True). No code compromise.
- **Files modified:** none beyond the planned research.py.

**2. [Rule 1 - Bug] Eval-guard grep tripped by my own docstring.**
- **Found during:** Task 2 full-suite verification.
- **Issue:** An explanatory docstring literally contained the string `literal_eval`, matching the acceptance grep `eval(\|exec(\|literal_eval`.
- **Fix:** Reworded to "never dynamic evaluation of model text" (commit `12dc4de`). No behavior change.

No authentication gates occurred.

## Known Stubs

None. The groundedness loop is fully wired to the live bridge and the fixture; scoring degrades to "keep all" only when the fixture is genuinely absent (documented behavior, not a stub).

## Self-Check: PASSED

- `flowstate/tools/research.py` — FOUND (contains both helpers, both constants).
- `tests/test_research_grounding.py` — FOUND.
- Commits `c1f1d42`, `12dc4de`, `8025c06` — FOUND in `git log`.
