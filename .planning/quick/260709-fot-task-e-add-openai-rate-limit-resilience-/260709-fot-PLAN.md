---
phase: 260709-fot
plan: 01
type: tdd
wave: 1
depends_on: []
files_modified:
  - bench/longmemeval_qa.py
  - tests/test_longmemeval_qa.py
autonomous: true
requirements: [TASK-E]
quick_task: true

must_haves:
  truths:
    - "_openai_chat constructs openai.OpenAI with max_retries=10 and timeout=120.0"
    - "A run where >30% of (item,arm) calls fail (empty answer or None judge) returns exit code 2 and marks JSON unreliable:true"
    - "A clean run (0 failures) returns 0 with unreliable:false and byte-identical accuracy math"
    - "--max-failure-rate is a tunable float threshold (default 0.30) honored by the guard"
    - "import bench.longmemeval_qa still works with openai NOT installed (lazy import preserved)"
  artifacts:
    - path: "bench/longmemeval_qa.py"
      provides: "SDK retry client + mass-failure guard"
      contains: "_OPENAI_MAX_RETRIES"
    - path: "tests/test_longmemeval_qa.py"
      provides: "offline tests for retry-client kwargs + failure guard"
      contains: "max_failure_rate"
  key_links:
    - from: "bench/longmemeval_qa.py:_openai_chat"
      to: "openai.OpenAI(max_retries, timeout)"
      via: "client construction"
      pattern: "openai\\.OpenAI\\("
    - from: "bench/longmemeval_qa.py:_run_qa"
      to: "output['unreliable'] / return 2"
      via: "failure_rate > args.max_failure_rate"
      pattern: "max_failure_rate"
---

<objective>
Make `bench/longmemeval_qa.py`'s OpenAI path survive low-TPM (429) throttling and NEVER
report a fake-low score from silent failures.

Purpose: A run under a 30k-TPM Tier-1 limit currently scores everything wrong silently
(empty answers + inconclusive judges counted as incorrect). Two additive changes fix this:
(1) SDK-level retry/backoff so calls ride out throttling; (2) a mass-failure guard that
fails LOUD (exit 2 + `unreliable:true` JSON) instead of emitting a plausible-but-fake score.

Output: Modified `bench/longmemeval_qa.py` + extended `tests/test_longmemeval_qa.py`.
Scope is STRICTLY these two files.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@/Users/jhogan/frameworx/CLAUDE.md

<interfaces>
<!-- Current state of the two functions being changed. Executor edits in place. -->

bench/longmemeval_qa.py — lazy OpenAI seam (~line 78):
```python
def _openai_chat(model: str, system: str, user: str) -> str | None:
    try:
        import openai
        client = openai.OpenAI()          # <- CHANGE 1 target
        resp = client.chat.completions.create(model=model, messages=[...], temperature=0, max_tokens=10)
        return resp.choices[0].message.content
    except Exception:
        return None
```

bench/longmemeval_qa.py — `_run_qa` scoring loop (~line 385) and tail (~line 425):
```python
answer = _answer_one(instance, ids, effective_reader_model, args.char_budget, provider=reader_provider)
judge = _judge_one(answer, instance, judge_model, provider=args.judge_provider)
# per_type_n / overall_n incremented; judge is True -> correct
...
total_n = sum(arm_data[arm]["overall"]["n"] for arm in arm_data)
output: dict = { "benchmark": "longmemeval_qa", ... "arms": arm_data }
if args.out is not None: args.out.write_text(json.dumps(output, indent=2))
# console summary table
return 1 if total_n == 0 else 0
```

tests/test_longmemeval_qa.py — the offline helper every _run_qa test uses (~line 60):
```python
def _make_args(tmp_path, *, backend="bm25", arms="retrieval", ..., sample=None, seed=0):
    return argparse.Namespace(backend=..., sample=sample, seed=seed)  # NO max_failure_rate yet
```
</interfaces>

Constraints (from CLAUDE.md + design spec):
- Modify ONLY `bench/longmemeval_qa.py` and `tests/test_longmemeval_qa.py`.
- `openai` stays lazily imported; module must import with openai NOT installed.
- Default path (claude reader + claude judge, no openai) stays byte-identical EXCEPT the
  additive JSON keys (`unreliable`, `failure_rate`, `judge_none`, `reader_empty`).
- ruff: line-length 100, double quotes, snake_case, `from __future__ import annotations`.
- Never-raises property preserved; only the existing deliberate prereq/canary hard-errors raise/return-1.
</context>

<tasks>

<task type="tdd" tdd="true">
  <name>Task 1: RED — failing tests for retry-client kwargs and the mass-failure guard</name>
  <files>tests/test_longmemeval_qa.py</files>
  <behavior>
    - Test A (retry client kwargs): inject a fake `openai` module into `sys.modules` whose
      `OpenAI(**kwargs)` records kwargs and whose `.chat.completions.create(**kw)` returns a
      stub response with `.choices[0].message.content == "ok"`. Call `qa._openai_chat("gpt-4o",
      "sys", "user")` → assert result == "ok" AND recorded `max_retries == 10` AND
      `timeout == 120.0`. Use `monkeypatch.setitem(sys.modules, "openai", fake_openai)` (via
      `types.ModuleType("openai")`), lazy-import-safe.
    - Test B (guard TRIGGERS): claude provider (no canary). Monkeypatch `_lme._build_docs`,
      `_r.bm25_rank`, and `qa._judge_one` to return None for all items (reader answer non-empty).
      With ≥4 single instances → judge_none == n, failure_rate == 1.0 > 0.30. Assert rc == 2,
      JSON has `unreliable is True`, `failure_rate > 0.30`, `judge_none == n`, `reader_empty == 0`,
      and the WARNING (substring "UNRELIABLE") was printed (capsys).
    - Test C (guard does NOT trigger): all clean (`_judge_one` True, non-empty answer) →
      rc == 0, `unreliable is False`, `failure_rate == 0.0`, accuracy math unchanged (overall
      accuracy == 1.0, n unchanged).
    - Test D (threshold boundary): 5 instances, exactly 2 with None judge (failure_rate 0.4),
      `--max-failure-rate` set to 0.5 → still reliable: rc == 0, `unreliable is False`.
    - Update `_make_args` helper: add `max_failure_rate: float = 0.30` param and include it in
      the returned `argparse.Namespace`. This is why existing _run_qa tests keep passing once
      `_run_qa` reads `args.max_failure_rate` directly (mirrors how `sample`/`seed` were added).
  </behavior>
  <action>Add `import sys` and `import types` to the test file's imports. Extend `_make_args`
    to accept and set `max_failure_rate` (default 0.30). Add the four tests above in a new
    section (mirror the existing offline monkeypatch idiom EXACTLY: patch collaborators on their
    owning module — `_lme`, `_r`, `qa`). For guard tests drive `qa._run_qa(args, instances)`
    directly with claude provider so no OpenAI canary fires. Reuse `_make_instances`; the
    `bench/fixtures/lme_smoke.json` fixture is available via `_FIXTURE` if an e2e variant is
    wanted (not required). Run `ruff check --fix tests/test_longmemeval_qa.py` yourself — the
    `import bench... as qa` idiom trips I001.
    These tests MUST FAIL now: `_openai_chat` does not pass kwargs, and `_run_qa` has no guard,
    no `max_failure_rate` read, and no `unreliable`/`failure_rate` keys.</action>
  <verify>
    <automated>python -m pytest tests/test_longmemeval_qa.py -q -k "retry or guard or unreliable or threshold or max_failure" 2>&1 | grep -Eq "failed|error"</automated>
  </verify>
  <done>New tests exist and FAIL (retry kwargs absent; guard/keys absent). `_make_args` sets
    `max_failure_rate`. ruff clean on the test file.</done>
</task>

<task type="tdd" tdd="true">
  <name>Task 2: GREEN — SDK retry client + mass-failure guard in longmemeval_qa.py</name>
  <files>bench/longmemeval_qa.py</files>
  <action>
    CHANGE 1 (retry/backoff): Add module constants near the lazy-seam header (~line 65):
    `_OPENAI_MAX_RETRIES = 10` and `_OPENAI_TIMEOUT = 120.0`. In `_openai_chat`, replace
    `client = openai.OpenAI()` with
    `client = openai.OpenAI(max_retries=_OPENAI_MAX_RETRIES, timeout=_OPENAI_TIMEOUT)`.
    The OpenAI SDK's built-in retry honors the 429 Retry-After header with exponential backoff
    + jitter — do NOT hand-roll a sleep loop. Everything else in `_openai_chat` unchanged;
    still never-raises, still returns None only after retries exhaust.

    CHANGE 2 (mass-failure guard) in `_run_qa`:
    - Before the arm loop, init run-level counters: `judge_none_count = 0`, `reader_empty_count = 0`.
    - Inside the inner scoring loop, AFTER `answer` and `judge` are computed and inside the
      per-instance try (before the accuracy tallies is fine): `if answer == "": reader_empty_count += 1`
      and `if judge is None: judge_none_count += 1`. Two INDEPENDENT signals — an item may
      increment both. Do NOT change the existing accuracy math (judge is True → correct; None → in n).
    - After `total_n = sum(...)`: compute
      `failure_rate = (judge_none_count + reader_empty_count) / max(1, total_n)` and
      `unreliable = failure_rate > args.max_failure_rate`.
    - Add to the `output` dict (additive keys, after `arms`): `"unreliable": unreliable`,
      `"failure_rate": failure_rate`, `"judge_none": judge_none_count`,
      `"reader_empty": reader_empty_count`. Write JSON as before (still write even when unreliable).
    - Return logic (replace the final `return 1 if total_n == 0 else 0`): keep
      `if total_n == 0: return 1` first (zero-scored path unchanged). Then
      `if unreliable:` print a prominent warning containing "UNRELIABLE" with the pct
      (e.g. `f"WARNING: results UNRELIABLE — {failure_rate * 100:.1f}% of reader/judge calls "
      `failed (empty answer or inconclusive judge), likely rate-limit/throttle (e.g. low OpenAI "
      `TPM). Not a real score."`) and `return 2`. Otherwise `return 0`.

    Add `--max-failure-rate` to `_build_parser`: `type=float, default=0.30`, dest resolves to
    `max_failure_rate`, help text noting it gates the unreliable-run guard. Read it in `_run_qa`
    via `args.max_failure_rate` (existing tests pass because Task 1 added it to `_make_args`).

    Preserve byte-identical default: 0 failures → failure_rate 0.0 → unreliable False → return 0,
    identical accuracy/JSON except the four additive keys.
  </action>
  <verify>
    <automated>python -m pytest tests/test_longmemeval_qa.py -q && ruff check bench/longmemeval_qa.py tests/test_longmemeval_qa.py && ruff format --check bench/longmemeval_qa.py tests/test_longmemeval_qa.py</automated>
  </verify>
  <done>All longmemeval_qa tests pass offline (no key/openai/claude). `_openai_chat` builds the
    client with max_retries=10, timeout=120.0. Guard returns 2 + `unreliable:true` above
    threshold, 0 + `unreliable:false` at/below. Default path byte-identical modulo additive keys.
    ruff check + format clean.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| harness → OpenAI API | 429/throttle and transient network errors cross here; SDK retry absorbs them |
| harness → results JSON | a throttled run must be labeled untrustworthy, not silently scored |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-fot-01 | Denial of Service (self-inflicted 429) | `_openai_chat` | mitigate | SDK `max_retries=10` + `timeout=120.0` honoring Retry-After backoff |
| T-fot-02 | Repudiation (fake score) | `_run_qa` output | mitigate | mass-failure guard: exit 2 + `unreliable:true` when failure_rate > threshold |
| T-fot-03 | Tampering (deps) | package installs | accept | no installs; openai already an optional [eval] extra, lazily imported |
</threat_model>

<verification>
- `python -m pytest tests/test_longmemeval_qa.py -q` passes OFFLINE (no OPENAI_API_KEY, no openai, no claude).
- `python -m pytest tests/ --cov=flowstate --cov-fail-under=80 -q` holds 80% (bench/ is out of the coverage target; no flowstate/ files touched).
- `ruff check bench/longmemeval_qa.py tests/test_longmemeval_qa.py && ruff format --check bench/longmemeval_qa.py tests/test_longmemeval_qa.py` clean.
- `python -c "import bench.longmemeval_qa"` works with openai NOT installed (lazy import preserved).
- `git diff --name-only` shows ONLY `bench/longmemeval_qa.py` and `tests/test_longmemeval_qa.py`.
  Proof that bench/longmemeval.py, bench/_retrieval.py, bench/grounding.py, flowstate/, pyproject.toml are UNCHANGED.
</verification>

<success_criteria>
- `_openai_chat` constructs `openai.OpenAI(max_retries=10, timeout=120.0)`; still never-raises.
- `--max-failure-rate` exists (float, default 0.30); guard returns 2 + `unreliable:true` above
  it, 0 + `unreliable:false` at/below, WARNING printed on the unreliable path.
- Zero-failure run: return 0, accuracy math + JSON byte-identical modulo the four additive keys.
- All tests pass offline; ruff clean; only the two target files changed.
</success_criteria>

<output>
Create `.planning/quick/260709-fot-task-e-add-openai-rate-limit-resilience-/SUMMARY.md` and
`.planning/quick/260709-fot-task-e-add-openai-rate-limit-resilience-/260709-fot-SUMMARY.md`
when done (status: complete).
</output>
