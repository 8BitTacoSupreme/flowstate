---
phase: quick-260629-kyl
plan: 01
type: tdd
wave: 1
depends_on: []
files_modified:
  - bench/tune_loop.py
  - tests/test_tune_loop.py
autonomous: true
requirements: [KYL-TUNE-LOOP]
must_haves:
  truths:
    - "The loop mines probe failures of a base answer-instruction (majority-False = failure)"
    - "It proposes ONE candidate instruction via a single claude --print call"
    - "It gates the candidate through bench.grounding._run_promptab and reads the verdict back"
    - "It emits a human-approval report (.json + .md) and HARD STOPS — never edits flowstate/ or any source"
    - "Every public function never raises; failures return safe sentinels and rc 1 from run_tune_loop"
    - "bench/grounding.py is imported, never modified"
  artifacts:
    - path: "bench/tune_loop.py"
      provides: "Manual prompt-tuning loop: _mine_failures, _propose_candidate, _gate, _emit_report, run_tune_loop, _build_parser, main"
      min_lines: 200
    - path: "tests/test_tune_loop.py"
      provides: "Offline tests (monkeypatched, no real claude/network) for every public function + the no-flowstate-writes guard"
      min_lines: 150
  key_links:
    - from: "bench/tune_loop.py"
      to: "bench.grounding"
      via: "from bench.grounding import _answer, _factcheck, _load_probes, _read_variant, _run_promptab, build_context_prefix, _LAYERS_MAP, MemoryStore"
      pattern: "from bench.grounding import"
    - from: "bench/tune_loop.py"
      to: "bench.judge._locate_claude"
      via: "subprocess idiom for the single candidate-proposal call"
      pattern: "from bench.judge import _locate_claude"
    - from: "_gate"
      to: "_run_promptab"
      via: "SimpleNamespace with variant_a/variant_b/layers/judge_models/trials/answer_model/root/out"
      pattern: "_run_promptab\\("
---

<objective>
Build `bench/tune_loop.py` — step 3 of the prompt-tuning A/B arc: a manual, opt-in loop that
mines probe failures of the live answer-instruction, proposes ONE candidate via a single claude
call, gates it through the existing `bench.grounding._run_promptab`, and emits a human-approval
report. It HARD STOPS at the report — it NEVER modifies any file under `flowstate/`, never edits
an adapter, never auto-applies. There is no `--apply` flag.

Purpose: close the prompt-tuning loop with a lab tool whose explicit boundary is the
human-approval gate. The human reads the report and makes the one change by hand.

Output: `bench/tune_loop.py` (new) + `tests/test_tune_loop.py` (new). bench/grounding.py and
everything under flowstate/ stay byte-for-byte unchanged.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@/Users/jhogan/frameworx/CLAUDE.md
@/Users/jhogan/frameworx/.planning/STATE.md

# Reuse these — do NOT reimplement. Import from bench.grounding.
@/Users/jhogan/frameworx/bench/grounding.py
@/Users/jhogan/frameworx/bench/fixtures/instr_baseline.txt
@/Users/jhogan/frameworx/bench/fixtures/instr_candidate.txt
@/Users/jhogan/frameworx/bench/fixtures/grounding_probes.example.json

# Mirror this offline test idiom in the NEW test file (monkeypatch _answer/_factcheck/subprocess).
@/Users/jhogan/frameworx/tests/test_bench_grounding.py

<interfaces>
<!-- VERIFIED signatures from bench/grounding.py — use exactly; do NOT re-derive. -->

# Reused symbols (import all from bench.grounding):
#   _answer(prefix, question, model, *, instruction="Answer concisely and specifically.") -> str   (never-raises; "" on failure)
#   _factcheck(answer, ground_truth, model) -> bool | None                                          (never-raises)
#   _load_probes(path: Path) -> list[dict] | None                                                   (never-raises; None on bad/missing/empty)
#   _read_variant(path: Path) -> str | None                                                         (never-raises)
#   build_context_prefix(root, mem, query=..., include_layers=...) -> str
#   _LAYERS_MAP[arm]  -> include_layers value; keys: none/pack/memory/wiki/full (also wikirag/wikivec — NOT used here)
#   MemoryStore(root=...)  -> context manager
#   _run_promptab(args, probes) -> int                                                              (never-raises)
#
# _locate_claude lives in bench.judge (grounding does `from bench.judge import _locate_claude`):
#   from bench.judge import _locate_claude   # _locate_claude() -> str | None

# _run_promptab reads these attributes off `args` (build a types.SimpleNamespace with EXACTLY these):
#   args.variant_a (Path), args.variant_b (Path), args.layers (list; uses layers[0]),
#   args.judge_models (comma STRING), args.trials (int), args.answer_model (str),
#   args.root (Path), args.out (Path | None)
# It writes its verdict JSON to args.out. The verdict JSON keys:
#   variant_a / variant_b : {accuracy, n, wilson_ci, text_sha}
#   delta, ci_overlap, decision   (decision is "ADOPT_B" or "NO_CHANGE")

# The non-retrieval per-probe prefix idiom (copy this shape for _mine_failures):
#   with MemoryStore(root=root) as mem:
#       prefix = build_context_prefix(root, mem, query=probe["question"], include_layers=_LAYERS_MAP[arm])
#   answer = _answer(prefix, probe["question"], answer_model, instruction=base_instruction)

# Subprocess idiom for the single candidate-proposal call (mirror _factcheck):
#   claude = _locate_claude()
#   if claude is None: return None
#   cmd = [claude, "--print", "--max-turns", "1", "--model", model, "--", prompt]
#   proc = subprocess.run(cmd, capture_output=True, text=True, timeout=...)
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1 (RED): Failing offline tests for the full tune loop</name>
  <files>tests/test_tune_loop.py</files>
  <action>
Create tests/test_tune_loop.py mirroring the offline idiom of tests/test_bench_grounding.py:
`import bench.tune_loop as t`, monkeypatch all LLM/subprocess boundaries so NO real claude
binary or network is ever touched. Reuse the `_Mem` stub MemoryStore and a `_bcp`-style
build_context_prefix stub. Every test asserts never-raises behavior.

Write these tests (all must FAIL initially because bench/tune_loop.py does not yet exist):

- `_mine_failures`: monkeypatch `t._answer`, `t._factcheck`, `t.build_context_prefix`, `t.MemoryStore`
  so some probes get a majority-True (pass) and some majority-False (fail). Assert only the failing
  probes are returned, each record has keys id/question/ground_truth/answer. Assert an empty answer
  ("") yields all-None votes → not majority → failure path works. Assert it never raises (force
  `_answer` to raise → returns []).

- `_propose_candidate`: empty failures list → returns None and `subprocess.run` is NOT called.
  With failures: monkeypatch `t._locate_claude` → "/bin/claude" and `t.subprocess.run` (or
  `subprocess.run`) to return rc=0 stdout="NEW INSTRUCTION" → assert returns the stripped string.
  rc!=0 → None. `_locate_claude()` returns None → None and no subprocess call.

- `_gate`: monkeypatch `t._run_promptab` to write a fake gate.json into ns.out (decision/delta/
  ci_overlap/variant_a/variant_b) and return 0. Assert `_gate` writes base/candidate instruction
  files into work_dir, then returns the parsed gate dict. Missing/unparseable gate.json → None.

- `_emit_report`: feed a gate dict with decision "ADOPT_B". Assert work_dir/tune_report.json and
  work_dir/tune_report.md both exist; the json has decision/base_sha/candidate_sha/n_failures/
  failure_ids/candidate_instruction; the .md CONTAINS the exact disclaimer substring
  "does not modify any source files". Also test decision NO_CANDIDATE path (gate=None) → json
  decision == "NO_CANDIDATE".

- `run_tune_loop` end-to-end (monkeypatch `t._mine_failures`, `t._propose_candidate`, `t._gate` as
  needed): happy path (failures → candidate → gate → report) returns 0 and a report dir under
  tmp_path. No-failures path (`_mine_failures` → []) → emits NO_CANDIDATE report, rc 0. Candidate
  None path → NO_CANDIDATE report, rc 0. Unreadable probes (`_load_probes` → None) → rc 1.
  never-raises: monkeypatch `t._mine_failures` to raise → run_tune_loop returns 1, no exception.

- CRITICAL no-source-writes guard: run the happy path with out_dir=tmp_path/run and assert every
  file the loop created lives under tmp_path (walk tmp_path), and assert NO path containing a
  "flowstate/" segment was written. (Construct args so out_dir is fully inside tmp_path.)

- `main` / `_build_parser`: `main(["--root", str(tmp_path), "--probes", str(probes_file),
  "--out-dir", str(tmp_path/"r")])` returns the rc of run_tune_loop (monkeypatch run_tune_loop to a
  sentinel, assert pass-through). Assert parser exposes --root/--probes/--base-instruction/--arm/
  --answer-model/--judge-models/--trials/--out-dir.

Use a SimpleNamespace or a small args factory to build the `args` object run_tune_loop consumes
(attributes: root, probes, base_instruction, arm, answer_model, judge_models, trials, out_dir).
  </action>
  <verify>
    <automated>python -m pytest tests/test_tune_loop.py -q 2>&1 | grep -E "error|ModuleNotFoundError|failed" | head</automated>
  </verify>
  <done>tests/test_tune_loop.py exists and fails (ModuleNotFoundError / assertion failures) because bench/tune_loop.py is not yet implemented. No test invokes a real claude binary.</done>
</task>

<task type="auto">
  <name>Task 2 (GREEN): Implement bench/tune_loop.py until tests pass</name>
  <files>bench/tune_loop.py</files>
  <action>
Create bench/tune_loop.py — a NEW file that IMPORTS from bench.grounding and does NOT modify it.
Header: module docstring stating this is a LAB TOOL that STOPS at an approvable report and NEVER
modifies any file under flowstate/ (no auto-apply, no --apply flag). Then `from __future__ import
annotations`; stdlib imports (argparse, json, subprocess, sys, hashlib, datetime/pathlib, types as
needed); `from bench.grounding import _answer, _factcheck, _load_probes, _read_variant,
_run_promptab, build_context_prefix, _LAYERS_MAP, MemoryStore`; `from bench.judge import
_locate_claude`. ruff format, line-length 100, double quotes, snake_case.

Implement EXACTLY (every public function wraps its body in try/except → safe sentinel; never raises):

1. `_mine_failures(root, probes, base_instruction, arm, answer_model, judge_models) -> list[dict]`
   (→ [] on error). For each probe: `with MemoryStore(root=root) as mem: prefix =
   build_context_prefix(root, mem, query=probe["question"], include_layers=_LAYERS_MAP[arm])`,
   `answer = _answer(prefix, probe["question"], answer_model, instruction=base_instruction)`.
   If answer == "" → votes = [None]*len(judge_models); else votes = [_factcheck(answer,
   probe["ground_truth"], m) for m in judge_models]. majority = (yes-count) > len(judge_models)/2.
   FAILURE when majority is False → append {"id","question","ground_truth","answer"}.

2. `_propose_candidate(base_instruction, failures, model) -> str | None` (→ None). Empty failures
   → return None (no subprocess). Else `_locate_claude()`; None → None. Build a prompt presenting
   the CURRENT instruction and each failure case (question + correct ground_truth + the wrong
   answer), asking for an improved single-line answer instruction; instruct OUTPUT ONLY the new
   instruction text, no preamble/markdown. `subprocess.run([claude, "--print", "--max-turns", "1",
   "--model", model, "--", prompt], capture_output=True, text=True, timeout=...)`. Return
   stripped stdout if rc==0 and non-empty, else None. Do not over-process multi-line responses.

3. `_gate(root, probes, base_text, candidate_text, arm, answer_model, judge_models, trials,
   work_dir) -> dict | None` (→ None). Write base_text → work_dir/base_instruction.txt and
   candidate_text → work_dir/candidate_instruction.txt. Build a `types.SimpleNamespace` ns with
   variant_a=base path, variant_b=candidate path, layers=[arm], judge_models=judge_models (comma
   STRING), trials=trials, answer_model=answer_model, root=root, out=work_dir/gate.json. Call
   `_run_promptab(ns, probes)`. Read+parse work_dir/gate.json → return dict; missing/unparseable
   → None.

4. `_emit_report(work_dir, base_text, candidate_text, failures, gate, arm) -> Path` (best-effort).
   sha(text) = hashlib.sha1(text.encode()).hexdigest()[:12]. Write work_dir/tune_report.json:
   {"arm", "n_failures", "failure_ids":[...], "base_sha", "candidate_sha",
   "gate": gate or None, "decision": gate["decision"] if gate else "NO_CANDIDATE",
   "candidate_instruction": candidate_text}. Write work_dir/tune_report.md with sections:
   Summary (decision, n_failures; if gate present include variant_a/variant_b accuracy + wilson_ci
   + delta + ci_overlap), Candidate Instruction (fenced block with full candidate_text), Mined
   Failures (list of failure id + question), and "Suggested action". The suggested-action text MUST
   say: if decision ADOPT_B, manually replace the answer instruction (e.g. the default in flowstate
   or the relevant adapter prompt) with the candidate after review; if NO_CHANGE/NO_CANDIDATE, say
   no change is warranted. The .md MUST include the exact disclaimer line:
   "This tool does not modify any source files. Apply manually after human review."
   Return the .md path.

5. `run_tune_loop(args) -> int` (try/except → 1). `_load_probes(args.probes)`; None → print note,
   return 1. base = `_read_variant(args.base_instruction) if args.base_instruction else
   _read_variant(Path("bench/fixtures/instr_baseline.txt"))`; None → note, return 1. mkdir
   args.out_dir (parents/exist_ok). `judge_list = [m.strip() for m in args.judge_models.split(",")
   if m.strip()]`. failures = _mine_failures(args.root, probes, base, args.arm, args.answer_model,
   judge_list). If no failures → _emit_report(out_dir, base, "", [], None, args.arm) with decision
   NO_CANDIDATE, print note + report path, return 0. Else candidate = _propose_candidate(base,
   failures, args.answer_model); None → emit NO_CANDIDATE report, return 0. Else gate = _gate(
   args.root, probes, base, candidate, args.arm, args.answer_model, args.judge_models, args.trials,
   out_dir)  # NOTE: pass the raw comma STRING args.judge_models into _gate (it forwards to ns for
   _run_promptab). report = _emit_report(out_dir, base, candidate, failures, gate, args.arm).
   Print console summary (decision + report path). Return 0.

6. `_build_parser()` + `main(argv=None) -> int`: flags --root (Path, required), --probes (Path,
   required), --base-instruction (Path, default None), --arm (default "none", choices
   none/pack/memory/wiki/full), --answer-model (default "sonnet"), --judge-models (default
   "sonnet,sonnet,opus"), --trials (int default 2), --out-dir (Path, default None →
   ./.tune_runs/<timestamp> created at run time). main parses args; if args.out_dir is None set a
   deterministic-enough default under ./.tune_runs; return run_tune_loop(args).
   `if __name__ == "__main__": sys.exit(main())`.

Pass the raw comma judge-models STRING to `_gate`/ns (because `_run_promptab` splits it itself);
pass the SPLIT list to `_mine_failures` (it loops judge models for `_factcheck`).
  </action>
  <verify>
    <automated>cd /Users/jhogan/frameworx && python -m pytest tests/test_tune_loop.py -q && ruff check bench/tune_loop.py tests/test_tune_loop.py && ruff format --check bench/tune_loop.py tests/test_tune_loop.py && python -m pytest tests/ --cov=flowstate --cov-fail-under=80 -q && git diff --quiet -- bench/grounding.py && git diff --quiet -- flowstate/ && echo GRD_AND_FLOWSTATE_UNCHANGED</automated>
  </verify>
  <done>tests/test_tune_loop.py passes; ruff check + format clean; the 80% flowstate coverage gate holds; `git diff` proves bench/grounding.py AND everything under flowstate/ are unchanged (only bench/tune_loop.py + tests/test_tune_loop.py added).</done>
</task>

</tasks>

<verification>
- `python -m pytest tests/test_tune_loop.py -q` passes.
- `python -m pytest tests/ --cov=flowstate --cov-fail-under=80 -q` holds the 80% gate.
- `ruff check bench/tune_loop.py tests/test_tune_loop.py` clean.
- `ruff format --check bench/tune_loop.py tests/test_tune_loop.py` clean.
- `git diff` shows ONLY bench/tune_loop.py and tests/test_tune_loop.py added/changed; bench/grounding.py and flowstate/ untouched.
- No test invokes a real claude binary or network (all boundaries monkeypatched).
</verification>

<success_criteria>
- bench/tune_loop.py implements _mine_failures, _propose_candidate, _gate, _emit_report,
  run_tune_loop, _build_parser, main — all never-raises.
- The loop HARD STOPS at the report: no --apply flag, no writes under flowstate/, bench/grounding.py
  imported not modified. Disclaimer present in both the module docstring and the emitted .md report.
- Candidate gated through bench.grounding._run_promptab via a SimpleNamespace; verdict read back.
- Tests cover every public function plus the no-source-writes guard, all offline.
</success_criteria>

<output>
Create `.planning/quick/260629-kyl-build-bench-tune-loop-py-manual-prompt-t/SUMMARY.md` and
`.planning/quick/260629-kyl-build-bench-tune-loop-py-manual-prompt-t/260629-kyl-SUMMARY.md`
when done (status: complete).
</output>
