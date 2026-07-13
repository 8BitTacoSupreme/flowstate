---
phase: 25-confinement-verification
reviewed: 2026-07-13T00:20:17Z
depth: deep
files_reviewed: 6
files_reviewed_list:
  - flowstate/sandbox.py
  - flowstate/bridge.py
  - flowstate/gsd_vendor.py
  - tests/test_sandbox.py
  - tests/test_bridge.py
  - tests/test_sandbox_e2e_macos.py
findings:
  critical: 1
  warning: 2
  info: 1
  total: 4
status: resolved
resolution:
  fixed: [CR-01, WR-01, WR-02]
  deferred: [IN-01]
  note: "CR-01/WR-01/WR-02 fixed via /gsd-code-review 25 --fix (commits 68eb4fe, b8f9c99, 6cf3538); 1335 tests @ 91.63%. IN-01 (Info, /tmp project_root shadow) deferred as out-of-scope."
---

# Phase 25: Code Review Report

> **Resolution (2026-07-13):** CR-01, WR-01, WR-02 fixed and committed on `main`
> (`68eb4fe` CR-01, `b8f9c99` WR-01, `6cf3538` WR-02) with integration tests across
> bridge/tools/pack/distiller/orchestrator; full suite 1335 passed @ 91.63% coverage.
> IN-01 (Info) intentionally deferred. Original findings preserved below.

**Reviewed:** 2026-07-13T00:20:17Z
**Depth:** deep
**Files Reviewed:** 6
**Status:** issues_found

## Summary

Reviewed the Phase 25 diff (`git diff 84dcead..HEAD -- flowstate/ tests/`) against the locked
D-01..D-04 decisions in `25-CONTEXT.md`. `flowstate/sandbox.py` itself is solid: the new
`SandboxUnavailableError` fail-loud dispatch is correctly scoped (confine-only, never
`observe`), the partial-capability carve-out (bwrap present / landlock absent still degrades
within confinement rather than raising) is implemented and unit-tested exactly as specified,
the `--tmpfs /tmp` addition to `build_linux_bwrap_args` is minimal and doesn't reopen an escape
(private, always-empty tmpfs; `--ro-bind / /` base and the out-of-root-write / `~/.ssh`-read
denials are untouched), and the `gsd_vendor.py` WR-2 change is genuinely comment-only — the
`*_TOKEN` scrub exemption was not widened.

The core defect is at the **integration boundary**: Phase 25 changed `wrap()`'s contract so
`confine` can now raise, but did not audit the real call sites that invoke `wrap(..., tier=...)`
with a caller-controlled sandbox value. None of `ClaudeBridge.run()`, `ToolAdapter.run_cmd()`,
`run_pack()`, `distiller._densify()`, or `orchestrator._run_step()` catch
`SandboxUnavailableError` — so a `sandbox=confine` run on a host lacking `bwrap`/`sandbox-exec`
crashes the pipeline with an unhandled traceback instead of the `Result`-object/BLOCKED-state
pattern used everywhere else in this codebase, and leaves `flowstate.json` with the failing
tool's status stuck at `RUNNING`. This satisfies the letter of D-01 ("never silently run
unconfined" — confirmed true, no bypass found) but not its practical safety: the guardrail's
first real invocation on an under-provisioned host will crash the CLI and corrupt run state,
and nothing in the test suite exercises this path at the integration level (only `sandbox.py`'s
own unit tests cover the raise).

A secondary, lower-severity finding: one of the new macOS E2E tests can't actually distinguish
the `project_root`-specific allow rule from the profile's always-on `/private/var/folders`
allow rule, because pytest's `tmp_path` fixture lives under `/private/var/folders` on macOS.

## Critical Issues

### CR-01: `SandboxUnavailableError` propagates uncaught through every real `wrap()` call site, crashing the CLI and corrupting pipeline state

**File:** `flowstate/bridge.py:310`, `flowstate/tools/base.py:82-107`, `flowstate/pack.py:118-141`, `flowstate/distiller.py:96-102`, `flowstate/orchestrator.py:139`

**Issue:**
`sandbox.py`'s `wrap()` now raises `SandboxUnavailableError` (a `RuntimeError` subclass) when
`tier="confine"` is requested and no confinement is achievable (D-01/SBX-06 — correctly
implemented in `sandbox.py` itself). But every production call site still only catches the
pre-Phase-25 exception set:

- `ClaudeBridge.run()` (`bridge.py:310`) calls `wrap(cmd, "llm", self.config.project_root, env, tier=self.config.sandbox)` **outside** the `try:` block that starts at line 323 — a raise here isn't caught by any `except` clause in `run()` at all (only `subprocess.TimeoutExpired` / `FileNotFoundError` around the `subprocess.run()` call are handled).
- `ToolAdapter.run_cmd()` (`tools/base.py:82`) calls `wrap(...)` inside a `try:` whose `except` clauses (lines 96, 102) only cover `FileNotFoundError` and `subprocess.TimeoutExpired` — `SandboxUnavailableError` passes straight through.
- `run_pack()` (`pack.py:119`) has the identical gap — only `TimeoutExpired`/`FileNotFoundError` are caught.
- `distiller._densify()` (`distiller.py:96`) calls `wrap(...)` **before** its own `try:` at line 97, so the raise isn't even inside the guarded region; this directly contradicts the file's own stated "Never raises" contract for the standalone `__main__` path (see the comment at `distiller.py:229`).
- `orchestrator._run_step()` (`orchestrator.py:139`) calls `result = execute_fn()` with no `try/except` around it at all. If any adapter's `execute()` eventually calls into a `confine`-tier `wrap()` that raises, the exception propagates out of `run_pipeline()` entirely: the `update_tool(..., status=ToolStatus.BLOCKED, ...)` and `save_state()` calls that would normally follow a failed step (lines 155/165) never run, so the tool's status stays wedged at `RUNNING` in `flowstate.json`, and the whole `flowstate run`/`init`/`pack` invocation dies with a raw Python traceback instead of the Rich-formatted `[red]Failed: ...[/red]` message every other failure mode produces.

This is not a confine-bypass (good — the fail-loud intent is honored, nothing runs unconfined
silently), but it is a crash + state-corruption bug directly caused by this phase's contract
change, and it is completely untested: `tests/test_bridge.py`, `tests/test_sandbox.py`, and
`tests/test_sandbox_e2e_macos.py` all test that `wrap()`/`_wrap_macos`/`_wrap_linux` raise
correctly in isolation, but no test drives a raise through `ClaudeBridge.run()`,
`ToolAdapter.run_cmd()`, `run_pack()`, `distiller._densify()`, or `orchestrator._run_step()` to
verify it degrades to a `Result(success=False, error=...)` / `BLOCKED` state rather than an
unhandled crash. Since there is currently no CLI/interview surface for setting
`preferences.sandbox = "confine"` (a documented Phase-24 deferral), this can only fire today via
a hand-edited `flowstate.json`, but that's exactly the population most likely to be dogfooding
the newly-shipped `confine` tier, and the phase's own stated goal is "the guardrail needs to be
trusted in production."

**Fix:**
Catch `SandboxUnavailableError` at each call site and convert it into the existing
result-object failure shape, mirroring the `FileNotFoundError`/`TimeoutExpired` handling already
present:

```python
# flowstate/bridge.py — wrap the wrap() call itself
from flowstate.sandbox import SandboxUnavailableError, wrap
...
try:
    cmd, env = wrap(cmd, "llm", self.config.project_root, env, tier=self.config.sandbox)
except SandboxUnavailableError as exc:
    return BridgeResult(success=False, output="", exit_code=-1, error=str(exc))
```

```python
# flowstate/tools/base.py:run_cmd — add SandboxUnavailableError to the except clause
from flowstate.sandbox import SandboxUnavailableError, wrap
...
except (FileNotFoundError, SandboxUnavailableError) as exc:
    return ToolResult(success=False, output="", error=str(exc))
```

```python
# flowstate/orchestrator.py:_run_step — don't let execute_fn() crash the pipeline
try:
    result = execute_fn()
except Exception as exc:
    update_tool(state, tool_name, status=ToolStatus.BLOCKED, error=str(exc))
    console.print(f"  [red]Failed: {exc}[/red]")
    save_state(state, root)
    if bus:
        bus.emit(StepFailed(payload={"tool": tool_name, "error": str(exc)}, source="orchestrator"))
    return None
```

Apply the equivalent pattern to `pack.py:run_pack()` and `distiller.py:_densify()` (move the
`wrap()` call inside the existing `try:`/add `SandboxUnavailableError` to its `except Exception`
clause). Add at least one integration-level test per call site (e.g., monkeypatch
`flowstate.bridge.wrap` to raise `SandboxUnavailableError` and assert `ClaudeBridge.run()`
returns `BridgeResult(success=False, ...)` instead of raising).

## Warnings

### WR-01: macOS E2E "write inside project_root succeeds" test doesn't isolate the property it claims to prove

**File:** `tests/test_sandbox_e2e_macos.py:65-72`
**Issue:** `test_write_inside_project_root_succeeds` writes to `tmp_path / "inside.txt"` where
`tmp_path` is pytest's tmp fixture — on macOS this resolves under `/private/var/folders/...`.
`build_macos_profile()` already unconditionally re-allows writes under `/private/var/folders`
(`sandbox.py:259-260`, independent of `project_root`). So this test would still pass even if the
`(subpath "{project}")` allow-rule were deleted entirely from `build_macos_profile` — it isn't
actually exercising the project-root-specific confinement rule, only the always-on tmp-dir
carve-out. This is the exact security property (D-03/SBX-05: "confined write to `$PROJECT` OK")
the phase's E2E test is documented as proving, so the false sense of coverage matters here more
than in an ordinary test.
**Fix:** Use a `project_root` that is provably outside `/private/tmp`, `/private/var/folders`,
and `/dev` (e.g., a directory created under `Path.home() / "flowstate_e2e_project"` and cleaned
up in a `finally`), so a write succeeding there can only be explained by the `project_root`
subpath allow-rule actually firing.

### WR-02: General subprocess exceptions beyond `TimeoutExpired`/`FileNotFoundError` still crash `ClaudeBridge.run()`, and the confine tier meaningfully widens this surface

**File:** `flowstate/bridge.py:323-378`
**Issue:** The `try/finally` added for WR-09 temp-profile cleanup only reintroduces the
pre-existing `except subprocess.TimeoutExpired` / `except FileNotFoundError` pair — any other
`OSError` (e.g. `PermissionError` if the `sandbox-exec`/`bwrap` binary located by
`_find_sandbox_exec()`/`_find_bwrap()` exists per `is_file()`/`which()` but isn't executable, or
an exec failure inside the Linux RUNG-1 `python -m flowstate.sandbox --apply-landlock` shim)
still propagates out of `run()` uncaught. This gap predates Phase 25, but wiring a real
`sandbox-exec`/`bwrap` subprocess wrapper (this phase's whole point) meaningfully increases how
often it can actually fire compared to the plain `claude` invocation this codebase shipped
before. The `finally` cleanup itself is correct (it still unlinks the profile on any exception),
but the caller above `run()` still crashes.
**Fix:** Broaden the catch to `except (subprocess.TimeoutExpired, FileNotFoundError, OSError)` (or add a dedicated `except OSError` branch) so any confine-tier spawn failure degrades to `BridgeResult(success=False, ...)` rather than an unhandled crash.

## Info

### IN-01: `build_linux_bwrap_args`'s `--tmpfs /tmp` mount can silently shadow `project_root` if `project_root == Path("/tmp")` (or a `/tmp` subpath)

**File:** `flowstate/sandbox.py:288-308`
**Issue:** bwrap applies mounts in argv order; `--bind project project` (line 293-295) is
listed before `--tmpfs /tmp` (line 296-297). If a caller ever configures `project_root` to be
exactly `/tmp` (or bind-mounts collide at the same path for some other reason — e.g. a CI
sandbox that defaults its workspace under `/tmp`), the later `--tmpfs /tmp` mount at an
identical mount point replaces the earlier bind, silently turning the "confined project" into an
always-empty scratch dir instead of the real project contents. This is a functional foot-gun,
not a security escape (the sandbox still denies writes everywhere else), and is a narrow edge
case — but worth a one-line doc note or an assertion in `build_linux_bwrap_args` guarding
against `project_root` resolving under `/tmp`.
**Fix:** Add a defensive check (or at least a docstring caveat) — e.g. `assert not str(project_root.resolve()).startswith("/tmp")` or reorder so the `--tmpfs /tmp` mount is emitted before the project bind (mount order for distinct, non-overlapping paths doesn't matter; only exact-path collisions do).

---

_Reviewed: 2026-07-13T00:20:17Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: deep_
