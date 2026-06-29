---
phase: quick-260629-gzd
plan: 01
type: tdd
wave: 1
depends_on: []
files_modified:
  - bench/grounding.py
  - bench/fixtures/strategy_scenarios.example.json
  - bench/fixtures/sys_strategy_baseline.txt
  - bench/fixtures/sys_strategy_candidate.txt
  - tests/test_bench_grounding.py
autonomous: true
requirements: [SYSAB-01]

must_haves:
  truths:
    - "Running `bench.grounding --mode sysab` A/B-tests two strategy system prompts and prints a decision."
    - "_generate_strategy returns generated doc text and never raises (returns '' on failure)."
    - "_judge_pairwise returns 'FIRST'/'SECOND'/None, position-debiased by caller, never raises."
    - "_run_sysab applies a Wilson-CI-vs-0.5 win-rate gate: ADOPT_B only when b_win_rate>0.5 AND wilson_low>0.5."
    - "Variant A defaults to the live STRATEGY_SYSTEM_PROMPT when --variant-a is omitted."
    - "All prior layers/RGB/promptab tests still pass; no existing logic modified."
  artifacts:
    - path: "bench/grounding.py"
      provides: "_generate_strategy, _judge_pairwise, _run_sysab, --scenarios flag, sysab dispatch"
      contains: "def _run_sysab"
    - path: "bench/fixtures/strategy_scenarios.example.json"
      provides: "2 scenario dicts (InterviewAnswers-shaped)"
    - path: "bench/fixtures/sys_strategy_baseline.txt"
      provides: "verbatim copy of STRATEGY_SYSTEM_PROMPT"
    - path: "bench/fixtures/sys_strategy_candidate.txt"
      provides: "candidate system prompt variant"
    - path: "tests/test_bench_grounding.py"
      provides: "offline sysab tests (helpers + decision + JSON shape)"
      contains: "sysab"
  key_links:
    - from: "bench/grounding.py main()"
      to: "_run_sysab"
      via: "dispatch on args.mode == 'sysab'"
      pattern: "args.mode == \"sysab\""
    - from: "_run_sysab"
      to: "flowstate.tools.strategy.STRATEGY_SYSTEM_PROMPT"
      via: "default variant A"
      pattern: "STRATEGY_SYSTEM_PROMPT"
---

<objective>
Add a fourth additive bench mode `--mode sysab` to `bench/grounding.py` that A/B-tests two
strategy-adapter system prompts. For each scenario it generates a strategy document per
variant (single-shot, canon-free), judges them pairwise against a 5-dimension rubric with
position-debiasing, and applies a Wilson-CI-vs-0.5 win-rate decision gate (ADOPT_B / NO_CHANGE).

Purpose: graduate the prompt-tuning A/B rig from step 1 (promptab, binary fact-check on an
answer) to step 2 (sysab, pairwise rubric judge on a generated DOCUMENT).
Output: 3 new functions + 1 new CLI flag + 1 extended choices tuple + 1 dispatch line in
bench/grounding.py; 3 fixtures under bench/fixtures/; offline tests in
tests/test_bench_grounding.py.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@/Users/jhogan/frameworx/CLAUDE.md
@.planning/quick/260629-gzd-add-mode-sysab-to-bench-grounding-py-sys/260629-gzd-PLAN.md

# The full design spec for this task lives in the planning_context that produced this plan.
# Implement EXACTLY that spec — ADD-ONLY, never-raises, no new third-party deps.

<interfaces>
<!-- Verified contracts — use directly, no codebase exploration needed. -->

bench/grounding.py (existing, MIRROR these — do NOT modify them):
- `_load_probes(path: Path) -> list[dict] | None`  (generic JSON-list loader — reuse for scenarios)
- `_read_variant(path: Path) -> str | None`  (reads+strips a text file; None on error)
- `_wilson(successes: int, n: int) -> tuple[float, float]`  (z=1.96 Wilson CI; n==0 → (0.0,0.0))
- `_factcheck(...)` — copy its subprocess idiom: `claude = _locate_claude(); cmd = [claude, "--print", "--max-turns", "1", "--model", model, "--", prompt]; subprocess.run(cmd, capture_output=True, text=True, timeout=_JUDGE_TIMEOUT)`
- `_run_promptab(args, probes) -> int` — MIRROR its try/except→1 shape, JSON-out block, console summary style, return-1-when-empty rule.
- module already imports: hashlib, json, re, subprocess, argparse, Path; `_locate_claude` from bench.judge.

flowstate.tools.strategy:
- `STRATEGY_SYSTEM_PROMPT: str`  (live prod prompt — DEFAULT for variant A)
- `_build_pressure_test_prompt(answers: InterviewAnswers) -> str`

flowstate.bridge:
- `ClaudeBridge(config: BridgeConfig | None = None, dry_run: bool = False)`
- `.run(prompt, *, system_prompt=None, allowed_tools=None, output_format="text", max_turns=None) -> BridgeResult`
- `BridgeResult` has `.success: bool`, `.output: str`
- `BridgeConfig(claude_bin=None, project_root=Path.cwd(), timeout=300, allowed_tools=[], max_turns=10, model=None, max_budget_usd=None, effort=None, inject_canon=True, enable_prompt_caching_1h=False)`

flowstate.state:
- `InterviewAnswers` — fields used: core_problem (str), ten_x_vision (str), milestones (list[str]), architecture_pattern (str), test_coverage (int)
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: RED — fixtures + failing offline sysab tests</name>
  <files>
    bench/fixtures/strategy_scenarios.example.json,
    bench/fixtures/sys_strategy_baseline.txt,
    bench/fixtures/sys_strategy_candidate.txt,
    tests/test_bench_grounding.py
  </files>
  <behavior>
    Write fixtures, then append a new clearly-commented "sysab mode" section to
    tests/test_bench_grounding.py. All tests OFFLINE (monkeypatch — no real claude / bridge /
    network), mirroring the promptab/RGB idiom (`import bench.grounding as g`, reuse `_bcp`/`_Mem`
    stubs only if a test calls main()).

    Fixtures:
    - strategy_scenarios.example.json: JSON list of 2 scenario dicts, each with keys
      id, question (short title), core_problem, ten_x_vision, milestones (2-3 strings),
      architecture_pattern, test_coverage. One streaming-data platform, one dev-tooling CLI.
    - sys_strategy_baseline.txt: EXACT verbatim copy of STRATEGY_SYSTEM_PROMPT text from
      flowstate/tools/strategy.py (lines 34-46, the dedented+stripped body) so a from-file
      variant A is byte-identical to the live constant.
    - sys_strategy_candidate.txt: same structure as baseline plus a believable improvement
      (e.g. "For each risk, state likelihood (high/med/low) and impact. Make the final
      Ship/Pivot/Kill call unambiguous and lead with it.").

    Tests (minimum):
    - test__generate_strategy_happy_and_failure: monkeypatch g.ClaudeBridge with a stub whose
      .run(...) returns an object with .success/.output → assert returns doc text; failing stub
      (success=False) → "" ; never raises.
    - test__judge_pairwise_parsing: monkeypatch g._locate_claude → "/bin/claude" and
      g.subprocess.run to return stdout "FIRST"/"SECOND"/"garbage" (rc=0) → "FIRST"/"SECOND"/None;
      _locate_claude→None → None.
    - test_sysab_adopt_b: monkeypatch g._generate_strategy to return distinct non-empty docs per
      variant, g._judge_pairwise so B wins BOTH orderings across enough scenarios×trials×judges
      that wilson_low > 0.5 → decision == "ADOPT_B", b_win_rate > 0.5.
    - test_sysab_no_change: judge splits 50/50 (B wins ordering1, A wins ordering2) → wilson_low
      <= 0.5 → decision == "NO_CHANGE".
    - test_sysab_json_shape: --out tmp file → assert keys mode=="sysab", adapter=="strategy",
      variant_a/variant_b (each with text_sha), comparisons, b_wins, b_win_rate, wilson_ci
      (2-list), decision.
    - test_sysab_variant_a_defaults_to_constant: omit --variant-a → variant_a.is_default_prompt
      is True AND variant_a.text_sha == sha1(STRATEGY_SYSTEM_PROMPT.encode()).hexdigest()[:12].
    - test_sysab_unreadable_scenarios: missing --scenarios file → main() returns 1, no raise.
    - test_sysab_unreadable_variant_b: missing --variant-b file → returns 1.

    Test plumbing notes: build a `_make_sysab_args(tmp_path, ...)` helper writing a scenarios
    file + variant files and returning argv with `--mode sysab --scenarios <f> --variant-b <f>
    --root <tmp> --probes <any-probes-file> --judge-models m1 --trials 1`. Note: --probes stays
    REQUIRED by the parser, so the helper must still pass a (throwaway) --probes file even though
    sysab ignores it. For decision/JSON/default tests monkeypatch g._generate_strategy AND
    g._judge_pairwise at the _run_sysab level (no bridge/subprocess at all). Only the two unit
    tests of the helpers stub g.ClaudeBridge / g._locate_claude+g.subprocess.run.
  </behavior>
  <action>
    Create the three fixtures, then append the sysab test section. Tests reference
    g._generate_strategy, g._judge_pairwise, g._run_sysab, and the --scenarios flag — all of
    which do NOT yet exist, so this task's tests MUST fail (RED). Do NOT implement grounding.py
    changes in this task. Copy STRATEGY_SYSTEM_PROMPT verbatim into the baseline fixture (read it
    from flowstate/tools/strategy.py; the value is the dedented body, stripped). Commit:
    `test(260629-gzd): add failing sysab tests + fixtures`.
  </action>
  <verify>
    <automated>python -m pytest tests/test_bench_grounding.py -q -k sysab 2>&1 | grep -qE "error|fail|Error|FAILED" && echo RED-OK</automated>
  </verify>
  <done>3 fixtures exist; new sysab test section appended; the sysab tests fail with AttributeError/missing-attr (RED), and all PRE-EXISTING tests (`-k "not sysab"`) still pass.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: GREEN — implement _generate_strategy, _judge_pairwise, _run_sysab + CLI wiring</name>
  <files>bench/grounding.py</files>
  <behavior>
    Add three new functions (never-raises) plus minimal additive CLI wiring. The ONLY edits to
    EXISTING lines permitted: extend the --mode choices tuple to include "sysab", and add the
    sysab dispatch line in main(). Everything else is pure addition.

    New imports (top of file, within existing flowstate dependency envelope):
      from flowstate.bridge import BridgeConfig, ClaudeBridge
      from flowstate.state import InterviewAnswers
      from flowstate.tools.strategy import STRATEGY_SYSTEM_PROMPT, _build_pressure_test_prompt

    _generate_strategy(answers, system_prompt, model) -> str: never-raises.
      prompt = _build_pressure_test_prompt(answers); bridge = ClaudeBridge(BridgeConfig(
      model=model, max_turns=1, allowed_tools=[], inject_canon=False)); br = bridge.run(prompt,
      system_prompt=system_prompt); return br.output.strip() if br.success and br.output.strip()
      else "". Comment WHY inject_canon=False + max_turns=1 + no tools (isolate the system
      prompt's effect on a single-shot generation; deliberate deviation from the adapter's
      WebSearch/max_turns=5). try/except → "".

    _judge_pairwise(scenario_question, doc_first, doc_second, model) -> str | None: never-raises.
      Use _locate_claude() + subprocess.run([claude, "--print", "--max-turns", "1", "--model",
      model, "--", prompt]) (mirror _factcheck — NOT the bridge). Prompt embeds the 5-dimension
      rubric (problem clarity, 10x potential, feasibility realism, risk identification quality,
      recommendation decisiveness), presents "DOCUMENT FIRST:" doc_first then "DOCUMENT SECOND:"
      doc_second, instructs reply with ONLY FIRST or SECOND. Parse with
      re.compile(r"\b(FIRST|SECOND)\b", re.IGNORECASE); first match → uppercased; None on no
      match / non-zero rc / no binary.

    _run_sysab(args, probes) -> int: never-raises (try/except → 1), mirror _run_promptab.
      - scenarios = _load_probes(args.scenarios); if None → note + return 1.
      - a_text = _read_variant(args.variant_a) if args.variant_a is not None else
        STRATEGY_SYSTEM_PROMPT; if args.variant_a given but a_text is None → note + return 1.
      - b_text = _read_variant(args.variant_b); if None → note + return 1.
      - judge_models = [m.strip() for m in args.judge_models.split(",") if m.strip()].
      - comparisons = 0; b_wins = 0.
      - For each scenario: answers = InterviewAnswers(core_problem=scenario.get("core_problem",""),
        ten_x_vision=scenario.get("ten_x_vision",""), milestones=scenario.get("milestones",[]),
        architecture_pattern=scenario.get("architecture_pattern",""),
        test_coverage=scenario.get("test_coverage",80)); scenario_question =
        scenario.get("question") or scenario.get("core_problem","").
        For trial in range(args.trials):
          doc_a = _generate_strategy(answers, a_text, args.answer_model)
          doc_b = _generate_strategy(answers, b_text, args.answer_model)
          if not doc_a or not doc_b: continue
          For each judge model run BOTH orderings (position-debias):
            ordering1: doc_first=doc_a, doc_second=doc_b → vote "SECOND" = B win.
            ordering2: doc_first=doc_b, doc_second=doc_a → vote "FIRST"  = B win.
            each ordering: comparisons += 1; map vote→B-win → b_wins += 1.
            (None vote counts as a comparison but NOT a B-win — document this.)
      - n = comparisons; b_win_rate = b_wins/n if n else 0.0; (low,high) = _wilson(b_wins, n).
      - decision = "ADOPT_B" if (b_win_rate > 0.5 and low > 0.5) else "NO_CHANGE".
      - text_sha(text) = hashlib.sha1(text.encode()).hexdigest()[:12].
      - JSON output (when args.out, wrapped in try/except print warning), exact shape:
        {"mode":"sysab","adapter":"strategy","n_scenarios":len(scenarios),"trials":args.trials,
        "answer_model":args.answer_model,"judge_models":[...],
        "variant_a":{"text_sha":...,"is_default_prompt":bool(args.variant_a is None)},
        "variant_b":{"text_sha":...},"comparisons":n,"b_wins":b_wins,"b_win_rate":b_win_rate,
        "wilson_ci":[low,high],"decision":decision}.
      - Always print console summary (header line; line with b_win_rate, wilson_ci, comparisons;
        final decision=... line) in _run_promptab visual style.
      - Return 1 when comparisons == 0, else 0.

    CLI (additive in _build_parser): add
      parser.add_argument("--scenarios", type=Path, default=None, help="JSON list of strategy
      scenarios for --mode sysab. sysab reads its input here; --probes stays required by the
      parser but is ignored by sysab (pass any probes file to satisfy it).")
      Extend --mode choices ("layers","rgb","promptab") → ("layers","rgb","promptab","sysab").
      REUSE existing --variant-a / --variant-b / --answer-model / --judge-models / --trials /
      --out / --root. Add NO other flags.

    Dispatch in main(): after the existing
      `if args.mode == "promptab": return _run_promptab(args, probes)`
    add (inside the same budget env-var try-block):
      `if args.mode == "sysab": return _run_sysab(args, probes)`.
  </action>
  <verify>
    <automated>python -m pytest tests/test_bench_grounding.py -q && ruff check bench/grounding.py tests/test_bench_grounding.py && ruff format --check bench/grounding.py tests/test_bench_grounding.py</automated>
  </verify>
  <done>All sysab tests pass GREEN; all prior promptab/rgb/layers tests still pass; ruff check + format clean; `git diff` shows the layers loop, RGB, _run_promptab/_read_variant, _answer, _factcheck, _wilson UNCHANGED — only additions plus the --mode choices tuple edit and the one main() dispatch line.</done>
</task>

</tasks>

<verification>
- `python -m pytest tests/test_bench_grounding.py -q` passes (all sysab + prior promptab/rgb/layers).
- `python -m pytest tests/ --cov=flowstate --cov-fail-under=80 -q` holds the 80% gate.
- `ruff check bench/grounding.py tests/test_bench_grounding.py && ruff format --check bench/grounding.py tests/test_bench_grounding.py` clean.
- `git diff bench/grounding.py` proof: the ONLY changes to existing lines are the --mode choices
  tuple and the main() sysab dispatch line; everything else is new functions/imports.
</verification>

<success_criteria>
- `bench.grounding --mode sysab --scenarios <f> --variant-b <f> --probes <any> --root <r>` runs,
  generates per-variant docs, judges pairwise position-debiased, and prints a decision.
- Variant A defaults to live STRATEGY_SYSTEM_PROMPT when --variant-a omitted (is_default_prompt
  True, matching text_sha).
- Decision gate is Wilson-CI-vs-0.5: ADOPT_B iff b_win_rate>0.5 AND wilson_low>0.5.
- Never-raises throughout (each new function and _run_sysab return safely on any failure).
- No third-party deps added; only bench/, bench/fixtures/, tests/ touched.
</success_criteria>

<output>
Create `.planning/quick/260629-gzd-add-mode-sysab-to-bench-grounding-py-sys/260629-gzd-SUMMARY.md`
and a bare `SUMMARY.md` in the same directory when done (status: complete).
</output>
