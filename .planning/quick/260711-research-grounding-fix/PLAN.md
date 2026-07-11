---
id: 260711-research-grounding-fix
type: quick
status: drafted
autonomous: true
files_modified:
  - flowstate/tools/research.py
  - tests/test_research_grounding.py
  - bench/ground.py
  - tests/test_ground.py
  - bench/verdict.py
  - .planning/phases/22-the-verdict/22-PREREGISTRATION.md
---

<objective>
Make the research arm participate in the Phase-22 verdict. Two locked fixes, ahead of
resuming the paid run:

- **Fix ②** (production correctness): `flowstate/tools/research.py` groundedness scoring
  fails CLOSED — a scorer bridge failure/timeout/unparseable-JSON returns `0.0`,
  discarding a successfully-generated section for a reason unrelated to its quality, and
  the report cannot distinguish "genuinely ungrounded" from "scorer was down". Make it
  fail OPEN and observable.
- **Fix ①** (bench setup): the real-repo bench path never grounds the pipeline in the
  subject repo, so `load_state` returns an empty interview → research's prompt is generic
  → every section scores low → empty `report.md`. Add a one-time auto-grounding step
  (`bench/ground.py::ground_from_repo`) that derives an interview from the repo via ONE
  bounded `claude --print` call, writes it into `flowstate.json`, and runs the repomix
  pack — called ONCE on `--root` before the sweep (never per-trial).

Locked (do NOT re-decide): auto-derive grounding in the bench; fix fail-closed scoring
now; keep the `0.6` threshold and the `retrieval_questions` criterion unchanged.

Purpose: unbias the verdict — every arm plans the REAL repo, and a down scorer never
silently empties the report.
Output: modified research adapter, new `bench/ground.py`, wired verdict setup,
preregistration addendum, full test coverage (bridge mocked, no real LLM).
</objective>

<context>
@flowstate/tools/research.py
@flowstate/bridge.py
@flowstate/pack.py
@bench/project.py
@bench/verdict.py
@tests/test_research_grounding.py

<interfaces>
<!-- Contracts the executor needs — extracted from codebase, no exploration required. -->

flowstate/state.py:
```python
class InterviewAnswers(BaseModel):
    research_focus: str = ""
    core_problem: str = ""
    ten_x_vision: str = ""
    milestones: list[str] = Field(default_factory=list)
    test_coverage: int = 80
    architecture_pattern: str = ""
    deployment_target: str = ""

def load_state(root: Path | None = None) -> FlowStateModel: ...
def save_state(state: FlowStateModel, root: Path | None = None) -> Path: ...
# FlowStateModel has .interview: InterviewAnswers
```

flowstate/bridge.py:
```python
# ClaudeBridge.run(prompt, *, system_prompt=None, allowed_tools=None,
#   output_format="text", max_turns=None, model=_SENTINEL) -> BridgeResult
# BridgeResult: success: bool, output: str, exit_code: int, error: str | None,
#   usage: BridgeUsage | None, duration_s: float | None
# In json mode the bridge ALREADY parses the envelope: on a dict payload with a
# string `result`, .output IS that result string (usage populated). On malformed/
# absent result, .output falls back to raw stdout and usage=None.
```

flowstate/pack.py:
```python
def run_pack(root: Path, *, compress: bool = False) -> PackResult:
    # PackResult: success, output_path: Path | None, exit_code, error
    # Returns success=False with a repomix-install-hint error when the binary is absent.
def _find_repomix() -> str: ...  # "" when repomix binary not locatable
```

bench/project.py:
```python
def scaffold(root: Path, *, synthetic: bool = True) -> None:
    # synthetic=False: preserves the real kickoff (flowstate.json, fixtures, pack,
    #   PROJECT.md, etc.), ONLY deletes memory.db. No synthetic fixture write.
```

bench/verdict.py (setup path):
```python
# _collect(root, mode, trials, runs, seed): real mode opens `with _worktree(root)
#   as target: scaffold(target); prepare_fixture.main(...); _real_arm_trajectories(...)`
# main(argv): parses --root/--mode; calls assert_pristine_worktree(root) then _collect(...).
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Research groundedness — fail-open + observable</name>
  <files>flowstate/tools/research.py, tests/test_research_grounding.py</files>
  <read_first>
    - flowstate/tools/research.py:117-147 (`_score_groundedness`), :149-247 (`execute`)
    - tests/test_research_grounding.py (existing helpers `_gen`, `_score`, `_write_fixture`, `_read_report`; mirror their style)
    - flowstate/bridge.py:320-335 (json-mode: `.output` is already the parsed `result` string; usage=None signals unparseable envelope)
  </read_first>
  <behavior>
    - `_score_groundedness` returns `None` (scorer-unavailable sentinel) when `br.success` is False.
    - `_score_groundedness` returns `None` when the bridge output has no clean integer to parse (ambiguous/unparseable) — do NOT fall through to `0.0`.
    - `_score_groundedness` returns `0.7` for a clean scoring result `"7"` (0-10 → 0.0-1.0, unchanged normalization).
    - `execute`: a section whose scoring returns `None` is KEPT (fail-open) and reported under a distinct "scorer-unavailable" bucket, NOT counted as discarded-low-score.
    - `execute`: a genuinely low score (< 0.6, scorer available) is still discarded.
    - `execute`: the `## Groundedness` report block lists scorer-unavailable topics separately from discarded topics.
    - `execute`: when `produced == 0`, the `ToolResult.error` distinguishes bridge-failed vs ungrounded/discarded vs scorer-unavailable (include the scorer `br.error` when available) so an empty report is attributable at a glance.
  </behavior>
  <action>
    Change `_score_groundedness` return type to `float | None`. Return `None` (not `0.0`)
    when `not br.success`. Parse the integer from the json-mode parsed result the bridge
    exposes on `.output` (per D-19 / bridge.py:324); if `re.search(r"-?\d{1,3}", br.output)`
    finds no match, return `None` (not `0.0`). Keep the existing `max(0, min(10, ...)) / 10.0`
    normalization for a real score. Capture the scorer `br.error` so `execute` can surface it.

    In `execute`, add a `scorer_unavailable_topics: list[str]` accumulator alongside
    `discarded_topics`. Update the measure→keep/discard loop (`:196-212`): after scoring,
    if `score is None`, KEEP the section (append it, `produced += 1`), record the topic in
    `scorer_unavailable_topics`, and skip the retry loop. Guard the retry loop and the
    `score >= _GROUNDEDNESS_THRESHOLD` comparison so `None` never hits the numeric `<`
    (a `None` short-circuits to keep-and-continue). This mirrors the existing
    `if not questions: keep all` fail-open philosophy at `:190-194`.

    Do NOT change `_GROUNDEDNESS_THRESHOLD` (0.6), `_load_retrieval_questions`, or the
    retrieval_questions criterion.

    Update the `## Groundedness` block (`:214-225`) to add a "Scorer-unavailable (kept):"
    line listing `scorer_unavailable_topics` (or "none"), keeping the existing Kept/Discarded
    lines. Update the `produced == 0` branch (`:227-240`) so `reasons` appends a distinct
    `scorer-unavailable: {topics} ({scorer br.error})` clause when applicable, keeping the
    existing bridge-failed and ungrounded/discarded clauses distinguishable.

    Add tests to tests/test_research_grounding.py (reuse `_gen`/`_score` helpers, MagicMock
    bridge): (a) `_score_groundedness` success=False → None; (b) unparseable output → None;
    (c) clean `"7"` → 0.7; (d) `execute` with a scorer returning failure keeps the section
    and the report/`## Groundedness` block names it scorer-unavailable; (e) a genuinely low
    score is still discarded; (f) `produced==0` error text distinguishes scorer-down from
    genuinely-ungrounded. Sequence per-topic bridge results via `side_effect`.
  </action>
  <verify>
    <automated>cd /Users/jhogan/frameworx && uv run python -m pytest tests/test_research_grounding.py -q && uv run ruff check flowstate/tools/research.py tests/test_research_grounding.py</automated>
  </verify>
  <acceptance_criteria>
    - `_score_groundedness` returns `float | None`; `None` on bridge-failure and on
      unparseable output; a real 0-10 still normalizes.
    - `execute` keeps scorer-unavailable sections (fail-open) and reports them in a bucket
      distinct from discarded-low-score.
    - `## Groundedness` block + `produced==0` error distinguish the three outcomes.
    - `0.6` threshold and retrieval_questions criterion unchanged.
    - New + existing tests green; ruff clean.
  </acceptance_criteria>
</task>

<task type="auto" tdd="true">
  <name>Task 2: bench/ground.py — auto-derive repo grounding</name>
  <files>bench/ground.py, tests/test_ground.py</files>
  <read_first>
    - flowstate/state.py InterviewAnswers / load_state / save_state (see &lt;interfaces&gt;)
    - flowstate/pack.py:75-149 (`run_pack`), :19-45 (`_find_repomix`)
    - flowstate/bridge.py:226-346 (`ClaudeBridge.run`, json-mode `.output` parsing)
    - bench/project.py:84-94 (`_interview` — shape of a fully-populated InterviewAnswers)
    - Note: an UNRELATED `bench/grounding.py` (RGB/promptab benchmark) already exists — this
      is a NEW, separate file `bench/ground.py`. Do NOT touch `bench/grounding.py`.
  </read_first>
  <behavior>
    - `ground_from_repo(root)` reads `root/README.md` (tolerate absence) + a bounded
      structural summary (top-level dirs + key source filenames, first N KB), makes ONE
      `ClaudeBridge.run(..., output_format="json", allowed_tools=[])` call, parses the
      returned JSON into `InterviewAnswers` fields (core_problem, ten_x_vision,
      architecture_pattern, milestones, research_focus).
    - Derived interview is written into `root/flowstate.json` via load_state/save_state —
      resulting `state.interview` is non-empty (research_focus / core_problem populated).
    - `run_pack(root)` is invoked; if repomix is absent, fail LOUD with the install hint
      (do not silently continue).
    - Runs ONCE per `root` (idempotent to re-run; not per-trial).
    - `python -m bench.ground --root <repo>` invokes `ground_from_repo` and returns exit 0
      on success, non-zero with a clear message on failure.
  </behavior>
  <action>
    Create `bench/ground.py` with `ground_from_repo(root: Path) -> None` (or a small result
    object) and a `main(argv=None)` + `if __name__ == "__main__"` argparse entry exposing
    `--root`.

    Implementation: read `root/README.md` if present (bounded slice, e.g. first ~8 KB);
    build a cheap structural summary from a bounded `os.scandir`/`Path.iterdir` walk of
    top-level dirs and key source files (bound total bytes — no full-tree crawl; reuse the
    repomix pack text if `.planning/codebase/repomix-pack.xml` already exists, else the cheap
    walk). Compose a single derivation prompt asking for STRICT JSON with keys
    `core_problem`, `ten_x_vision`, `architecture_pattern`, `milestones` (list),
    `research_focus`. Call `ClaudeBridge(...).run(prompt, output_format="json",
    allowed_tools=[], max_turns=2, model="sonnet")`. Parse `br.output` with `json.loads`
    inside try/except; on failure, raise a clear RuntimeError (fail loud — the derivation is
    a one-time gate, not a graceful-degrade path).

    Load state via `load_state(root)`, populate `state.interview = InterviewAnswers(...)`
    from the parsed fields (coerce `milestones` to `list[str]`), `save_state(state, root)`.

    Guard repomix BEFORE packing: if `_find_repomix()` returns `""`, raise a RuntimeError
    carrying the same install hint `run_pack` uses ("repomix CLI not found. Install repomix
    or set FLOWSTATE_REPOMIX_BIN..."). Then call `run_pack(root)`; if the result is not
    `success`, raise with `result.error`.

    stdlib + flowstate only — no new deps.

    Create tests/test_ground.py (mock the derivation bridge call — MonkeyPatch `ClaudeBridge`
    or inject a stub returning a `BridgeResult` with json `.output`; mock/patch `run_pack`
    and `_find_repomix` so no real repomix runs): (a) `ground_from_repo` populates a non-empty
    `InterviewAnswers` in `flowstate.json` (assert research_focus / core_problem set from the
    mocked derivation); (b) it calls `run_pack(root)` once; (c) repomix-absent (`_find_repomix`
    → "") raises with the install hint; (d) `main(["--root", str(tmp)])` returns 0 on success.
    Write a minimal `README.md` under tmp so the read path is exercised.
  </action>
  <verify>
    <automated>cd /Users/jhogan/frameworx && uv run python -m pytest tests/test_ground.py -q && uv run ruff check bench/ground.py tests/test_ground.py</automated>
  </verify>
  <acceptance_criteria>
    - `bench/ground.py::ground_from_repo(root)` exists; makes ONE bounded json-mode bridge
      call; writes a non-empty interview to `flowstate.json`; runs `run_pack`.
    - Fails loud with an install hint when repomix is absent.
    - `python -m bench.ground --root <repo>` works; exit 0 on success.
    - Unrelated `bench/grounding.py` untouched.
    - Tests green (bridge + pack mocked, no real LLM/repomix); ruff clean.
  </acceptance_criteria>
</task>

<task type="auto">
  <name>Task 3: Wire grounding into the verdict setup + preregistration addendum</name>
  <files>bench/verdict.py, .planning/phases/22-the-verdict/22-PREREGISTRATION.md, tests/test_ground.py</files>
  <read_first>
    - bench/verdict.py:258-270 (`_collect` real path: `_worktree` → `scaffold(target)` →
      prepare_fixture), :576-620 (`main` setup: `assert_pristine_worktree` then `_collect`)
    - bench/project.py:192-223 (`scaffold(synthetic=False)` preserves interview + pack, wipes
      memory.db only)
    - .planning/phases/22-the-verdict/22-PREREGISTRATION.md (frozen win rule / arms / n — do
      NOT change; append a setup addendum only)
  </read_first>
  <action>
    Wire the ONE-TIME grounding into the real-mode setup so it runs on `--root` BEFORE the
    sweep (never per-trial — a per-trial LLM call would vary across arms and confound the
    paired design). In `bench/verdict.py`, import `ground_from_repo` and call it once in the
    real-mode setup of `main` (before `_collect`, guarded to `args.mode == "real"`), so the
    grounded `flowstate.json` + repomix pack are frozen on `--root` and every `_worktree`
    copy inherits them via `scaffold(synthetic=False)`. Cheap mode must NOT call it (no spend,
    stays deterministic). Keep it minimal — do not restructure `_collect`.

    Append a setup addendum to 22-PREREGISTRATION.md documenting the auto-grounding step:
    "Before the sweep, the subject repo is grounded once via an auto-derived interview
    (one bounded `claude --print` call, `bench/ground.py::ground_from_repo`) plus a repomix
    pack, frozen into `flowstate.json` — constant across all arms/trials; only the context
    layers differ." State EXPLICITLY that this does NOT change the frozen decision rule
    (CI-excludes-0 AND d≥0.8 AND Holm-reject), the 5 arms, or n.

    Add a test to tests/test_ground.py (or a new small test module) asserting the
    preservation contract: build a `root` with a grounded `flowstate.json` (non-empty
    interview) + a `.planning/codebase/repomix-pack.xml`, then call
    `bench.project.scaffold(root, synthetic=False)` and assert the interview + pack survive
    while `memory.db` is deleted.
  </action>
  <verify>
    <automated>cd /Users/jhogan/frameworx && uv run python -m pytest tests/test_ground.py -q && uv run python -m pytest bench/ -q 2>/dev/null; uv run python -m bench.verdict --mode cheap >/dev/null && uv run ruff check bench/verdict.py</automated>
  </verify>
  <acceptance_criteria>
    - `ground_from_repo` is called exactly once in real-mode setup, before the sweep; cheap
      mode never calls it.
    - `bench/verdict.py --mode cheap` still green end-to-end (deterministic, no spend).
    - `scaffold(synthetic=False)` preservation test passes (interview + pack survive,
      memory.db wiped).
    - 22-PREREGISTRATION.md carries the setup addendum; frozen win rule / arms / n unchanged.
    - ruff clean.
  </acceptance_criteria>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| subject repo → derivation prompt | untrusted repo README/source text enters ONE bounded `claude --print` call |
| derivation response → flowstate.json | model-produced JSON is parsed and written to state |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-22gf-01 | Tampering | `ground_from_repo` derivation output | mitigate | parse with `json.loads` in try/except; coerce fields to declared `InterviewAnswers` types; raise (fail loud) on malformed JSON rather than writing garbage state |
| T-22gf-02 | Denial of Service | derivation bridge call | mitigate | single call, `output_format="json"`, `allowed_tools=[]`, bounded `max_turns=2`; bounded README/structural-summary input (first N KB, no full-tree crawl) |
| T-22gf-03 | Information Disclosure | repo content in prompt | accept | derivation reads only the subject repo the operator already controls; no secret exfiltration path beyond the existing bridge |
| T-22gf-04 | Elevation of Privilege | bench pack step | mitigate | repomix run via existing `run_pack`; repomix absence fails loud with install hint, no silent shell fallback |
| T-22gf-SC | Tampering | npm/pip/cargo installs | mitigate | none — stdlib + flowstate/bench only, no new dependencies added |
</threat_model>

<verification>
- `uv run python -m pytest tests/ -q` — full suite green, ≥80% coverage
  (`--cov-fail-under=80` enforced by pyproject.toml).
- `uv run ruff check .` clean.
- `uv run python -m bench.verdict --mode cheap` green (grounding not invoked in cheap mode).
- No new runtime dependencies (stdlib + flowstate/bench only).
</verification>

<success_criteria>
- Research groundedness scoring fails OPEN: a down/unparseable scorer keeps the section and
  is reported distinctly from a genuine low-score discard.
- `bench/ground.py::ground_from_repo` derives a non-empty interview from the subject repo via
  ONE bounded claude call, writes it to `flowstate.json`, runs the repomix pack, and fails
  loud when repomix is absent.
- Grounding is wired into the verdict as a ONE-TIME `--root` setup step (never per-trial);
  cheap mode stays deterministic and free.
- `scaffold(synthetic=False)` provably preserves the grounded interview + pack while wiping
  memory.db.
- 22-PREREGISTRATION.md documents the setup addendum without altering the frozen win
  rule / arms / n.
- Full suite green (≥80%), ruff clean, no new deps.
</success_criteria>

<output>
Create `.planning/quick/260711-research-grounding-fix/SUMMARY.md` and
`.planning/quick/260711-research-grounding-fix/260711-research-grounding-fix-SUMMARY.md`
(both, per the repo SUMMARY-frontmatter convention) with `status: complete` when done.
</output>
