---
phase: quick-260710-ffo
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - bench/BENCHMARKING_SCOPE.md
  - bench/PAIRED_DESIGN_RUNBOOK.md
  - bench/BENCHMARK_HANDOFF.md
autonomous: true
requirements:
  - FFO-DOC-01
  - FFO-DOC-02
must_haves:
  truths:
    - "A reader can determine which benchmark files license retrieval-ranking claims vs harness-value claims, and cannot conflate them"
    - "The stale 'Prerequisite code changes' section of PAIRED_DESIGN_RUNBOOK.md correctly marks #1 and #2 as LANDED and #3 as the only unbuilt item"
    - "All three bench docs cross-link to each other"
    - "The dead-alias trio (autoresearch/gstack/superpowers) is recorded as deleted-on-migration, not a persuasion/trust-boundary architecture"
    - "No .py file, test, or pyproject.toml is modified"
  artifacts:
    - path: "bench/BENCHMARKING_SCOPE.md"
      provides: "Two-track benchmark model (retrieval component vs harness value)"
      min_lines: 60
      contains: "Track 1"
    - path: "bench/PAIRED_DESIGN_RUNBOOK.md"
      provides: "Corrected runbook with landed/unbuilt status"
      contains: "LANDED"
    - path: "bench/BENCHMARK_HANDOFF.md"
      provides: "One-line cross-link pointer to the two new/fixed docs"
      contains: "BENCHMARKING_SCOPE"
  key_links:
    - from: "bench/BENCHMARKING_SCOPE.md"
      to: "bench/PAIRED_DESIGN_RUNBOOK.md"
      via: "cross-link"
      pattern: "PAIRED_DESIGN_RUNBOOK"
    - from: "bench/PAIRED_DESIGN_RUNBOOK.md"
      to: "bench/BENCHMARKING_SCOPE.md"
      via: "cross-link"
      pattern: "BENCHMARKING_SCOPE"
    - from: "bench/BENCHMARK_HANDOFF.md"
      to: "bench/BENCHMARKING_SCOPE.md"
      via: "one-line pointer"
      pattern: "BENCHMARKING_SCOPE"
---

<objective>
Correct the benchmarking record so a retrieval-vs-harness category error cannot recur. Two docs-only deliverables:

1. Create `bench/BENCHMARKING_SCOPE.md` — the authoritative two-track model (Track 1: retrieval component, deterministic, no LLM; Track 2: harness value, output-quality). Records what each track licenses, what it cannot license, the honest NULL harness result, the absence of any token/cost/latency accounting, the unenforced evaluator independence, and the dead-alias trio that an external review mistook for a persuasion/trust-boundary architecture.
2. Fix `bench/PAIRED_DESIGN_RUNBOOK.md` — its "Prerequisite code changes" section is stale and misleading: two of three items already shipped. Mark #1 and #2 LANDED (with the shipped implementation being better than proposed), leave #3 as the only unbuilt item, correct the "gain comes from the pack" expectation with the measured wiki/semantic result, and flag that the proven-lift wiki layer has no production caller and no corpus on disk.

Purpose: Prevent the next operator from re-deriving landed work or citing a track's numbers for the wrong kind of claim.
Output: One new doc, one corrected doc, one one-line pointer added to the handoff. No code touched.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@bench/BENCHMARK_HANDOFF.md
@bench/PAIRED_DESIGN_RUNBOOK.md

House style to match (from BENCHMARK_HANDOFF.md): measured-not-estimated framing, `file:line` citations, terse tables, an explicit integrity-rules section. Every quantitative claim below was verified against the codebase this session — cite the given `file:line` refs, do not re-derive, do not contradict.

CONSTRAINT — DOCS ONLY: Do NOT modify any `.py` file, any test, or `pyproject.toml`. This task is additive/corrective documentation only.
</context>

<tasks>

<task type="auto">
  <name>Task 1: Create bench/BENCHMARKING_SCOPE.md (two-track model)</name>
  <files>bench/BENCHMARKING_SCOPE.md</files>
  <action>
Create a new doc in the house style of BENCHMARK_HANDOFF.md (measured-not-estimated, `file:line` citations, terse tables, integrity-rules section). State the two-track benchmark model so a retrieval-vs-harness category error cannot recur. Include, at minimum, these sections:

**Header** — date 2026-07-10, one-line purpose, and the measured-not-estimated disclaimer. Add a cross-link line pointing to `BENCHMARK_HANDOFF.md` (measured results) and `PAIRED_DESIGN_RUNBOOK.md` (harness-value experiment protocol).

**Track 1 — Retrieval component.** Files: `bench/longmemeval.py`, `bench/locomo.py`, shared `bench/_retrieval.py`. Metrics: `recall_all@k` / `recall_any@k` / evidence-coverage. State plainly: ZERO LLM involvement — fully deterministic. Critical framing: BM25 here is the INCUMBENT implementation, not an arbitrary external baseline — v0.6.0 replaced FTS5/BM25 with semantic KNN inside `MemoryStore.get_context()` (`flowstate/memory.py`, `_semantic_results`, `_SEMANTIC_MAX_DISTANCE = 0.89` ≈ cosine 0.60), so semantic-vs-BM25 is the counterfactual for a change already shipped. State what this track licenses (claims about retrieval ranking ONLY) and what it cannot license (harness value). Measured table (n=500, real longmemeval_s_cleaned.json): BM25 recall_all@5 = 0.844, chunked-semantic (bge-small, 400-tok) = 0.866 — note overlapping Wilson CIs, no paired significance test run yet; recall_any@5 = 0.966 for BOTH; recall_all@10 = 0.946 (dense) / 0.904 (BM25).

**Track 2 — Harness value.** Files: `bench/compound_eval.py`, `bench/replicate.py`, `bench/metrics.py`, `bench/judge.py`, `bench/report.py`. Arms via `_LAYERS_MAP` (`bench/compound_eval.py:60-66`): `full` (None = all layers), `none` (frozenset() = vanilla control), `pack` ({"fixtures","pack"} = naive code RAG), `memory` ({"gotchas","memory","since_last_run"} = compounding), `wiki` ({"fixtures","wiki"} = distilled knowledge). State that `bench/metrics.py` computes the AUTHORITATIVE 4-axis `CompoundingScore` deterministically — its only imports are `dataclasses`, `itertools.pairwise`, `typing.Literal` (stdlib); the single "judge" match in that file is the English word in a line-6 docstring. The LLM judge is Tier-2 and EXPLICITLY EXCLUDED: `bench/report.py:80` reads `"note": "Tier-2 output-quality judge — EXCLUDED from compounding_score"`. State what this track licenses (whether the context stack improves output quality per token spent) and what it cannot license (retrieval ranking).

**Known state to record honestly** — a section with these three facts:
- The harness-value experiment already ran and came back NULL: Cohen's d 0.29 at K=3/N=5; the K=8/N=10 d=0.62 was a run-0 noise artifact; in absolute quality the control arm ended HIGHER (off 7.6 vs on 7.0). Cross-reference PAIRED_DESIGN_RUNBOOK.md "Why this run (context)".
- No token, cost, or latency accounting exists anywhere in `bench/`. `prefix_tokens` (`bench/metrics.py:51`, `bench/capture.py:186`) is `len(prefix) // 4` — an input-context estimate, not consumption. `ClaudeBridge.run()` accepts `output_format="json"` (`flowstate/bridge.py:197,230`) and its docstring cites `usage.cache_read_input_tokens`, but no caller ever passes it and `BridgeResult` has no `usage` field (fields: `success, output, exit_code, error`).
- Evaluator independence is not enforced. `bench/judge.py` shells out to `claude` (deliberately NOT `flowstate.bridge`) to grade artifacts that `flowstate.bridge` produced via `claude`. Nothing requires judge-model ≠ producer-model.

**Dead-alias table** — reproduce as a terse table citing `flowstate/state.py:63-65` (`_OLD_TOOL_KEYS`): `autoresearch`→`research` (split-topic `claude --print` calls); `gstack`→`strategy` (one `claude --print` pressure-test call); `superpowers`→`discipline` (pure-Python git/tests/hooks audit, ZERO LLM calls — `flowstate/discipline.py:1` docstring: "Discipline module — pure Python project audit (replaces superpowers.py)."). Note these keys are deleted on state migration, asserted at `tests/test_state.py:92-94`. Then state plainly: an external review mistook these three dead aliases for a three-tier "Cialdini persuasion / trust-boundary / deep-domain-hunting" compliance architecture. No such layers exist; none are installed as skills or plugins. `flowstate/`'s only enforcement primitive is `flowstate/verify.py`'s mechanical acceptance gates (coverage threshold + produced-artifact integrity); everything else honestly SKIPs.

**Integrity rules** — a short section in the spirit of BENCHMARK_HANDOFF.md §6: never cite a Track-1 number to license a Track-2 claim or vice versa; never quote a harness-value number as if token/cost accounting existed; never present the dead aliases as an architecture; name the track alongside every metric.

Do NOT place fenced code blocks that look like implementations; small inline `file:line` citations and terse markdown tables only. Do not modify any `.py` file.
  </action>
  <verify>
    <automated>test -f bench/BENCHMARKING_SCOPE.md && grep -q "Track 1" bench/BENCHMARKING_SCOPE.md && grep -q "Track 2" bench/BENCHMARKING_SCOPE.md && grep -q "EXCLUDED from compounding_score" bench/BENCHMARKING_SCOPE.md && grep -q "compound_eval.py:60-66" bench/BENCHMARKING_SCOPE.md && grep -q "PAIRED_DESIGN_RUNBOOK" bench/BENCHMARKING_SCOPE.md && grep -q "superpowers" bench/BENCHMARKING_SCOPE.md && git diff --name-only | grep -vqE '\.(py)$|pyproject\.toml' && ! git diff --name-only | grep -qE '\.py$'</automated>
  </verify>
  <done>bench/BENCHMARKING_SCOPE.md exists with both tracks, the NULL result, the no-cost-accounting fact, the unenforced-independence fact, the dead-alias table with the debunk, an integrity-rules section, and a cross-link to the runbook. No .py file changed.</done>
</task>

<task type="auto">
  <name>Task 2: Fix PAIRED_DESIGN_RUNBOOK.md and add BENCHMARK_HANDOFF.md pointer</name>
  <files>bench/PAIRED_DESIGN_RUNBOOK.md, bench/BENCHMARK_HANDOFF.md</files>
  <action>
Correct `bench/PAIRED_DESIGN_RUNBOOK.md` in place. Preserve all still-valid content — do NOT delete the runbook. Specifically preserve: the arm-attribution interpretation (`pack−none` / `memory−none` / `full−pack`), the cost reality, the verdict rules, and the "If compounding is null again — the upgrade path" section. Corrections:

Rewrite the "Prerequisite code changes (do these first)" section so it no longer reads as pending work. Mark status inline:
- #1 `--layers {full,none,pack,memory}` replacing `--inject on|off` → **LANDED.** `_LAYERS_MAP` at `bench/compound_eval.py:60-66` (also added a `wiki` arm). Note the shipped implementation is BETTER than the runbook proposed: it threads a first-class `include_layers` kwarg gated at assembly time (`flowstate/context_prefix.py`, `_run_one` monkeypatch at `bench/compound_eval.py:169-179`) rather than the post-hoc `## `-heading string filtering the runbook originally suggested. Keep/annotate the original proposal text as historical, but clearly marked superseded.
- #2 `--paired` within-trial run-0 normalization → **LANDED.** `_paired_normalize` at `bench/replicate.py:60-67` (`[[s - t[0] for s in t] for t in trials]`), plus `--layers` nargs at `bench/replicate.py:100-106`. Raw and paired metrics are both computed; `--paired` selects which drives Cohen's d.
- #3 multi-judge in `judge.py` → **STILL UNBUILT** (the only remaining item). Note `bench/grounding.py` already has the pattern to copy: `--judge-models` default `"sonnet,sonnet,opus"` at `bench/grounding.py:1136`, majority vote + `_wilson`.

Correct the runbook's stated expectation (currently in "Why this run" / interpretation) that "most quality gain on a large repo comes from the pack/RAG": the later grounding bench measured raw code pack ≈ none, while distilled wiki + semantic retrieval hit 0.825 ≈ oracle 0.800 (surfaced the right article 17/20 vs BM25's 3/20). Add these corrections without deleting the original attribution logic — mark the superseded expectation.

Flag the wiki gap honestly: the wiki layer has no production caller (deferred WIKI-F1 — no `flowstate/` module passes `include_layers={"wiki"}`; every caller is a bench/test driver), and neither `.planning/codebase/wiki.md` nor `.planning/codebase/wiki/` exists on disk — so the one layer with a proven lift never fires. Also note the corpus mismatch: `bench/wikigen.py` writes the single-file `wiki.md`, while the Phase-11 semantic wiki retriever reads the ARTICLE DIRECTORY `.planning/codebase/wiki` (`flowstate/context_prefix.py:54,64`) — a real gap.

Add a cross-link line near the top of the runbook pointing to `BENCHMARKING_SCOPE.md` (the two-track model / what this experiment can and cannot license) and `BENCHMARK_HANDOFF.md`.

Then add a single one-line pointer into `bench/BENCHMARK_HANDOFF.md` (e.g. near the top after the date line, or in §1) directing readers to `BENCHMARKING_SCOPE.md` for the two-track model and `PAIRED_DESIGN_RUNBOOK.md` for the harness-value protocol. Keep it to one line; do not restructure the handoff.

Do not modify any `.py` file.
  </action>
  <verify>
    <automated>grep -q "LANDED" bench/PAIRED_DESIGN_RUNBOOK.md && grep -q "compound_eval.py:60-66" bench/PAIRED_DESIGN_RUNBOOK.md && grep -q "replicate.py:60-67" bench/PAIRED_DESIGN_RUNBOOK.md && grep -q "STILL UNBUILT" bench/PAIRED_DESIGN_RUNBOOK.md && grep -q "grounding.py:1136" bench/PAIRED_DESIGN_RUNBOOK.md && grep -q "0.825" bench/PAIRED_DESIGN_RUNBOOK.md && grep -q "WIKI-F1" bench/PAIRED_DESIGN_RUNBOOK.md && grep -q "context_prefix.py:54,64" bench/PAIRED_DESIGN_RUNBOOK.md && grep -q "BENCHMARKING_SCOPE" bench/PAIRED_DESIGN_RUNBOOK.md && grep -q "BENCHMARKING_SCOPE" bench/BENCHMARK_HANDOFF.md && grep -q "upgrade path" bench/PAIRED_DESIGN_RUNBOOK.md && ! git diff --name-only | grep -qE '\.py$'</automated>
  </verify>
  <done>Runbook marks #1/#2 LANDED and #3 STILL UNBUILT with correct file:line refs, corrects the pack-gain expectation with the 0.825 wiki result, flags the WIKI-F1 no-caller + missing-corpus + single-file-vs-directory gap, preserves the upgrade-path and attribution sections, and cross-links to BENCHMARKING_SCOPE.md. BENCHMARK_HANDOFF.md has a one-line pointer. No .py file changed.</done>
</task>

</tasks>

<verification>
- Both new/edited docs match the BENCHMARK_HANDOFF.md house style (file:line citations, terse tables, integrity framing).
- All three docs cross-link: BENCHMARK_HANDOFF ↔ BENCHMARKING_SCOPE ↔ PAIRED_DESIGN_RUNBOOK.
- `git diff --name-only` contains only the three markdown files — no `.py`, no test, no `pyproject.toml`.
- Every quantitative claim traces to a verified file:line ref; none contradicts the verified facts.
</verification>

<success_criteria>
- `bench/BENCHMARKING_SCOPE.md` exists and unambiguously separates retrieval-ranking claims (Track 1) from harness-value claims (Track 2), records the NULL harness result, the absent cost accounting, the unenforced evaluator independence, and debunks the dead-alias "architecture".
- `bench/PAIRED_DESIGN_RUNBOOK.md` no longer instructs the reader to build already-shipped `--layers`/`--paired` support; #3 multi-judge stands as the only open item; the pack-gain expectation is corrected; the wiki no-caller/no-corpus gap is flagged; still-valid content preserved.
- Docs-only: no `.py`, test, or `pyproject.toml` change.
</success_criteria>

<output>
Create `.planning/quick/260710-ffo-correct-benchmarking-record/260710-ffo-SUMMARY.md` (and a bare `SUMMARY.md` in the same dir) when done, with `status: complete` in the frontmatter.
</output>
