# Phase 25: Confinement + Verification - Pattern Map

**Mapped:** 2026-07-12
**Files analyzed:** 7 (3 code modifications, 2 test files, 2 verification/doc artifacts)
**Analogs found:** 7 / 7 (all analogs are in-tree; no external pattern needed)

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|-----------------|---------------|
| `flowstate/sandbox.py` (modify: fail-loud raise, D-01) | utility (confinement dispatch) | request-response / transform | `flowstate/sandbox.py:_apply_landlock_syscalls` (raise) vs `check_bwrap_available` (never-raise) — same file, contrasting precedent | exact (in-file) |
| `flowstate/bridge.py` (modify: live confined spawn + WR-09 cleanup) | service | request-response / file-I/O | `bench/replicate.py:_run_trial` (mkstemp + try/finally unlink around `subprocess.run`) | role-match (closest cross-file temp-file-lifecycle-around-subprocess) |
| `flowstate/gsd_vendor.py` (modify: WR-2 doc comment) | service | event-driven (npm install) | `flowstate/gsd_vendor.py` itself, existing SBX-03/D-02 comment at `:326-330` | exact (in-file) |
| `tests/test_sandbox.py` (modify: fail-loud + tightened-rung tests) | test | request-response | `tests/test_sandbox.py` itself (existing `monkeypatch.setattr("flowstate.sandbox.sys.platform", ...)` dispatch tests) | exact (in-file) |
| `tests/test_bridge.py` (modify: temp-profile cleanup test) | test | file-I/O | `tests/test_bridge.py:test_run_builds_correct_command` (fake-binary + real `subprocess.run` through `ClaudeBridge.run()`) | exact |
| new `tests/test_sandbox_e2e_macos.py` (or similar) | test | request-response / file-I/O | `tests/test_discipline.py` (`_git_missing = shutil.which(...) is None` + `@pytest.mark.skipif`) | role-match (closest binary/platform-gated real-subprocess skip pattern; no direct darwin-skip precedent exists) |
| new `.planning/phases/25-confinement-verification/25-SPIKE-LINUX-REPROBE.md` (or similar committed verification doc) | config (verification artifact) | batch (one-shot recorded probe) | `.planning/phases/23-linux-parity-core-seam/23-SPIKE-LINUX.md` | exact |

## Pattern Assignments

### `flowstate/sandbox.py` — D-01 fail-loud raise (utility, request-response)

**Analog:** itself — two competing in-file precedents the new code must choose between and reconcile.

**The degrade/fallback code D-01 REPLACES for the confine case** (`wrap()` dispatch, lines 164-170):
```python
    # tier == "confine" — platform dispatch, profile builders below.
    if sys.platform == "darwin":
        return _wrap_macos(cmd, project_root, scrubbed_env)
    if sys.platform.startswith("linux"):
        return _wrap_linux(cmd, project_root, scrubbed_env)
    # Unsupported platform: env-scrub only, never hard-fail (D-03 posture).
    return cmd, scrubbed_env
```
The last line (unsupported platform → silent observe-fallback) is exactly what D-01 says must now raise when `tier == "confine"`.

**`_wrap_linux`'s RUNG-3 observe-fallback D-01 tightens** (lines 531-540):
```python
    if not check_bwrap_available():
        global _bwrap_warning_emitted
        if not _bwrap_warning_emitted:
            print(
                "bwrap unavailable — falling back to observe (env-scrub only); "
                "kernel confinement pending",
                file=sys.stderr,
            )
            _bwrap_warning_emitted = True
        return cmd, env
```
Per D-01, this print-and-degrade-to-observe shape must become a raise ONLY when the caller explicitly requested `confine` (which is always true here — `_wrap_linux` is only reached from `wrap()`'s `tier == "confine"` branch, so this entire fallback becomes the raise site verbatim; no observe-vs-confine branching needed inside `_wrap_linux` itself).

**`_find_sandbox_exec`'s silent fallback D-01 tightens** (lines 451-467):
```python
def _find_sandbox_exec() -> str:
    """Locate the `sandbox-exec` binary.
    ...
    """
    env_path = os.environ.get("FLOWSTATE_SANDBOX_EXEC_BIN")
    if env_path and Path(env_path).is_file():
        return env_path

    found = shutil.which("sandbox-exec")
    if found:
        return found

    return "/usr/bin/sandbox-exec"
```
The `"/usr/bin/sandbox-exec"` guess-and-hope-it-exists fallback is the thing D-01 replaces for the confine case — `_wrap_macos` (or its caller) must verify this path is real (or that `check_bwrap_available()`-style functional check passes) before dispatching, not just assume it.

**Raise pattern to copy** — `_apply_landlock_syscalls` is the file's own precedent for "this specific failure must be observable, not swallowed" (contrast with `_apply_landlock`'s wrapping `except Exception: return` a few lines above it, which is the D-03 asymmetric-degrade posture this phase does NOT touch):
```python
    if ruleset_fd < 0:
        raise OSError("landlock_create_ruleset failed")
    ...
    if rc != 0 or not all_ok:
        raise OSError("landlock ruleset application failed — restriction was not fully applied")
```

**Install-hint message wording to copy** — the project's established "$BINARY not found. Install X or set $ENV_VAR to the binary path." shape, used identically by `_find_claude` (`bridge.py:161-171`) and `_find_repomix` error path (`pack.py:94-102`):
```python
    if not config.repomix_bin:
        return PackResult(
            success=False,
            exit_code=1,
            error=(
                "repomix CLI not found. Install repomix or set "
                "FLOWSTATE_REPOMIX_BIN to the binary path."
            ),
        )
```
The new `SandboxUnavailableError` message should mirror this exact "not found. Install X or set FLOWSTATE_..._BIN to the binary path." phrasing, per-platform (`sandbox-exec` / macOS install hint vs `bwrap` / Linux package-manager hint).

**Custom-exception precedent (there is none in flowstate/*.py outside vendor/node_modules)** — the codebase uses plain stdlib exceptions exclusively (`ValueError`, `OSError`); see `installer.py:104-107`:
```python
def _assert_within(base: Path, dest: Path) -> None:
    """Refuse any destination that resolves outside ``base`` (path traversal guard)."""
    if base != dest and base not in dest.parents:
        raise ValueError(f"refusing to write outside .claude: {dest}")
```
and `verify.py:164-166`:
```python
            if acceptance_gates_raw is not None and not isinstance(acceptance_gates_raw, list):
                raise ValueError(
                    f"acceptance_gates must be a list, got {type(acceptance_gates_raw).__name__}"
                )
```
No project file defines a custom `class FooError(Exception)` — CONTEXT.md leaves "the exact exception type/name" to the planner's discretion, but the house style favors a plain, single-purpose exception class (e.g. `class SandboxUnavailableError(RuntimeError)`) with a clear message, not a hierarchy. `OSError` (already used in this exact file for landlock failures) is the strongest same-file precedent if the planner prefers to reuse a stdlib type instead of defining a new class.

**Module docstring contract-change note** (lines 1-12) — the "never raises" wording that must be scoped down:
```python
"""Subprocess confinement seam — env-scrub (`observe`) + platform confinement (`confine`).

Exposes a graceful-degradation seam: importing this module NEVER requires
`bwrap`/Landlock/`sandbox-exec` to be present, and the `observe` tier never
blocks or fails a subprocess call — it is pure env hygiene, not hard
confinement (D-01). `wrap()` never spawns the *target* `cmd` itself; it
transforms `(argv, env)` for the caller to pass to `subprocess.run()`
unchanged (D-04).
```
Per D-01/CONTEXT.md, this docstring must be edited so "never blocks or fails" is explicitly scoped to `observe` + the availability *probes*, and a new paragraph documents that `confine` now raises `SandboxUnavailableError` (or chosen name) when no confinement is achievable at all.

---

### `flowstate/bridge.py` — WR-09 temp-profile cleanup + live confined spawn (service, file-I/O)

**Analog:** `bench/replicate.py:_run_trial` (lines 40-93) — the closest existing "create a temp artifact, spawn a subprocess, guarantee cleanup regardless of outcome" shape in the codebase.

**Current call site to modify** (`bridge.py:296-320`):
```python
        # "--" separates CLI flags from the positional prompt.
        cmd.append("--")
        cmd.append(prompt)

        # Unset CLAUDECODE env var to allow nested invocation
        env = {**os.environ}
        env.pop("CLAUDECODE", None)
        # Opt-in: raise cache TTL from 5 min to 1 h for eligible API-key accounts
        if self.config.enable_prompt_caching_1h:
            env["ENABLE_PROMPT_CACHING_1H"] = "1"

        cmd, env = wrap(cmd, "llm", self.config.project_root, env, tier=self.config.sandbox)

        try:
            start = time.monotonic()
            result = subprocess.run(
                cmd,
                cwd=self.config.project_root,
                capture_output=True,
                text=True,
                timeout=self.config.timeout,
                env=env,
            )
```
`wrap()` already returns the transformed `(cmd, env)`; on macOS confine, `cmd[0:3]` is `[sandbox-exec, "-f", <temp .sb path>]` per `_wrap_macos` (sandbox.py:470-493). Nothing currently unlinks that temp path after the child exits — this is the WR-09 leak CONTEXT.md's Claude's-Discretion section assigns to this call site.

**try/finally temp-file-cleanup pattern to copy** (`bench/replicate.py:53-92`):
```python
    # mkstemp returns (open_fd, path); close the fd immediately so it does not
    # leak, and unlink the file in the finally below so a full sweep
    # (trials x arms x 2 invocations) cannot exhaust the fd limit or litter TMPDIR.
    fd, path = tempfile.mkstemp(prefix=f"repl_{label}_", suffix=".json")
    os.close(fd)
    out = Path(path)
    cmd = [...]
    try:
        proc = subprocess.run(cmd, check=False)
        if proc.returncode != 0:
            print(f"[replicate] {label}: compound_eval exited {proc.returncode}", flush=True)
            return None
        raw = out.read_text()
    except OSError as exc:
        print(f"[replicate] {label}: no/unreadable output ({exc})", flush=True)
        return None
    finally:
        out.unlink(missing_ok=True)
```
The `finally: out.unlink(missing_ok=True)` shape (unconditional cleanup, `missing_ok=True` so a file that's already gone or was never a confine-tier profile is a no-op, not an error) is exactly the pattern to wrap around `bridge.py`'s existing `subprocess.run()` call. Detect the macOS confine shape by checking `cmd[0]` against the located `sandbox-exec` path (or simpler: check `tier == "confine" and sys.platform == "darwin"`) and unlink `cmd[2]` (the profile path, per `_wrap_macos`'s returned argv shape `[sbx, "-f", profile_path, *cmd]`) in a `finally` around the existing `try/except subprocess.TimeoutExpired/FileNotFoundError` block already at `bridge.py:311-365`.

**Existing error-handling shape to preserve unchanged** (`bridge.py:352-365`) — the `finally` block must nest around, not replace, this:
```python
        except subprocess.TimeoutExpired:
            return BridgeResult(
                success=False,
                output="",
                exit_code=-1,
                error=f"claude CLI timed out after {self.config.timeout}s",
            )
        except FileNotFoundError:
            return BridgeResult(
                success=False,
                output="",
                exit_code=-1,
                error=f"claude CLI not found at: {self.config.claude_bin}",
            )
```

---

### `flowstate/gsd_vendor.py` — WR-2 doc comment (service, event-driven)

**Analog:** itself — the existing SBX-03/D-02 comment this phase extends, not replaces.

**Current comment to extend** (`gsd_vendor.py:325-330`):
```python
        try:
            # SBX-03/D-02: default observe tier — refresh() is NOT project-scoped
            # (its only caller, `gsd_version --refresh`, has no `root`/resolve_root()
            # call), so no ProjectPreferences.sandbox is threaded here; Path.cwd() is
            # the correct placeholder since observe ignores project_root.
            cmd, env = wrap(cmd, "tool", Path.cwd(), {**os.environ})
```
Per D-04, add a WR-2 note here (and near the second `wrap()` call at `:386-391`) documenting that `observe`'s denylist strips `*_TOKEN`-suffixed vars (including `NPM_TOKEN`), which would break a private-registry `npm install` — this is accepted/documented, not fixed. No functional code change, comment only.

---

### `tests/test_sandbox.py` — fail-loud + tightened-rung tests (test, request-response)

**Analog:** itself — the existing platform-dispatch monkeypatch tests already establish the exact mocking shape.

**Pattern to copy** (`tests/test_sandbox.py:142-155`):
```python
    def test_unsupported_platform_confine_returns_scrubbed(self, monkeypatch):
        monkeypatch.setattr("flowstate.sandbox.sys.platform", "sunos5")
        ...
        # not fall through into real confinement dispatch. Force the platform
        # back to darwin ...
        monkeypatch.setattr("flowstate.sandbox.sys.platform", "darwin")
```
This existing test (`test_unsupported_platform_confine_returns_scrubbed`) asserts the OLD behavior D-01 replaces — it must be rewritten to assert `pytest.raises(SandboxUnavailableError)` (or chosen name) instead of a scrubbed-passthrough return. Same shape (`monkeypatch.setattr("flowstate.sandbox.sys.platform", ...)`) extends directly to the new Linux-RUNG-3-now-raises tests, reusing the `platform.release()` monkeypatch pairs already established at `tests/test_sandbox.py:352-386` (`monkeypatch.setattr("flowstate.sandbox.sys.platform", "linux")` + `monkeypatch.setattr("flowstate.sandbox.platform.release", lambda: "...")`).

---

### `tests/test_bridge.py` — temp-profile cleanup test (test, file-I/O)

**Analog:** `tests/test_bridge.py:test_run_builds_correct_command` (lines 65-83) and `bench/test_bench_replicate.py`'s WR-02 cleanup-assertion tests.

**Fake-binary-through-real-run pattern to copy** (`tests/test_bridge.py:65-83`):
```python
def test_run_builds_correct_command(tmp_path: Path):
    """Verify the command structure without actually executing."""
    fake_claude = tmp_path / "claude"
    fake_claude.write_text("#!/bin/sh\necho test-output")
    fake_claude.chmod(0o755)

    config = BridgeConfig(claude_bin=str(fake_claude), project_root=tmp_path)
    bridge = ClaudeBridge(config=config)

    result = bridge.run("Hello", system_prompt="Be helpful", allowed_tools=["Read", "Bash"], max_turns=5)
    assert result.success
    assert "test-output" in result.output
```
Extend this shape with `config.sandbox = "confine"` (macOS-only, or monkeypatch `sys.platform`) and assert the temp `.sb` file referenced by `wrap()`'s returned argv no longer exists after `bridge.run()` returns — mirroring the assertion style in `tests/test_bench_replicate.py:294-311`:
```python
def test_run_trial_removes_temp_file_on_success(monkeypatch):
    ...
    scores = rep._run_trial("wiki", 2, Path("."), "wiki0")
    assert scores == [5.0, 7.0]
    assert not Path(captured["out"]).exists(), "temp file must be unlinked"
```
and the failure-path pairing at `tests/test_bench_replicate.py:314-331` (cleanup fires even when the underlying operation errors).

---

### new `tests/test_sandbox_e2e_macos.py` — E2E denial proof (test, request-response / file-I/O)

**Analog:** `tests/test_discipline.py:1-24` — the closest existing "skip if the real dependency is absent, then exercise a REAL subprocess (not mocked)" pattern in the suite. No file in the codebase currently gates a test on `sys.platform` for real (non-monkeypatched) execution — this is a genuinely new pattern, so this analog is role-match, not exact.

**Skip-gate pattern to copy** (`tests/test_discipline.py:1-24`):
```python
"""Tests for discipline module — pure Python project audit."""

import shutil
import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest

from flowstate import discipline
...

# Genuine subprocess.run, captured before any monkeypatch so routers can
# delegate real git calls while stubbing the pytest invocation.
_REAL_RUN = subprocess.run

_git_missing = shutil.which("git") is None


def _init_repo(path: Path) -> None:
    """Create a real git repo with one commit (offline, deterministic)."""
    _REAL_RUN(["git", "init"], cwd=path, check=True, capture_output=True)
    ...
```
and the decorator usage (`tests/test_discipline.py:124, 184`):
```python
@pytest.mark.skipif(_git_missing, reason="git binary not available")
```
Translate directly: `_not_darwin = sys.platform != "darwin"` module-level bool, `@pytest.mark.skipif(_not_darwin, reason="macOS sandbox-exec only")` on the test function(s), and a real (non-monkeypatched) `flowstate.sandbox.wrap(..., tier="confine")` + `subprocess.run()` invocation of a real `claude --print` call (per the D-03 macOS E2E spec: confined write to `$PROJECT` succeeds, write to `$HOME` denied, read of `~/.ssh` denied, auth via Keychain survives). This test needs the WR-09 cleanup (bridge.py or a local equivalent) wired first so it doesn't leak `.sb` files on every CI run.

---

### new Linux verification artifact (`.planning/phases/25-confinement-verification/25-SPIKE-LINUX-REPROBE.md` or similar) — config/doc, batch

**Analog:** `.planning/phases/23-linux-parity-core-seam/23-SPIKE-LINUX.md` — the exact committed-artifact shape D-03 says to mirror.

**Frontmatter + structure to copy** (`23-SPIKE-LINUX.md:1-20`):
```markdown
---
status: complete
phase: 23-linux-parity-core-seam
plan: 04
requirement: SBX-01
verdict: PARITY PROVEN
date: 2026-07-12
---

# 23-SPIKE-LINUX.md — SBX-01 Linux bwrap+landlock Spike Finding

Mirrors the passed macOS Seatbelt spike (see memory `flowstate-sandbox-spike`). Retires the
milestone's gating unknown: does a Linux `bwrap`+landlock allow-default + selective-deny profile
confine filesystem writes while preserving `claude` auth and API reachability?

## 1. Environment
...
## 2. Mechanism result ...
## 3. Auth-preservation result ...
```
The new artifact must record: (a) the D-02 re-probe using the EXACT shipped `build_linux_bwrap_args` argv (read-only `HOME`, no `--setenv HOME /tmp/chome` shortcut) with the FILE-based `~/.claude/.credentials.json` credential — NOT the token-path shortcut the original spike used (`23-SPIKE-LINUX.md`'s own auth section notes `--setenv HOME /tmp/chome` — this is precisely the divergence D-02 exists to close); (b) the D-03 denial assertions (write outside `project_root` denied, `~/.ssh` read denied); one shared Docker run serves both D-02 and D-03 per CONTEXT.md's explicit instruction to not duplicate the harness.

## Shared Patterns

### Locator pattern (already established, no new work needed)
**Source:** `flowstate/pack.py:_find_repomix` (lines 21-47), mirrored by `flowstate/sandbox.py:_find_bwrap` (lines 409-425, explicit "mirrors `flowstate/pack.py:_find_repomix`" docstring) and `_find_sandbox_exec` (lines 451-467).
**Apply to:** any new locator logic in the fail-loud path — resolution order is always: 1) `FLOWSTATE_*_BIN` env var (must be an existing file) → 2) `shutil.which()` PATH search → 3) fallback/failure.
```python
def _find_bwrap() -> str:
    """Locate the `bwrap` binary.

    Resolution order (mirrors `flowstate/pack.py:_find_repomix`):
    1. `FLOWSTATE_BWRAP_BIN` env var (must point to an existing file)
    2. `shutil.which("bwrap")` (PATH search)
    3. `""` — not found; `check_bwrap_available()` already gates on this.
    """
```
D-01's fail-loud raise hooks onto this "not found" (`""`) result — no new locator needed, just a new caller-side decision on what to do with it.

### Install-hint error message wording
**Source:** `flowstate/bridge.py:_find_claude` error path (lines 256-265) and `flowstate/pack.py:run_pack` (lines 94-102).
**Apply to:** the new `SandboxUnavailableError` message.
```python
        if not self.available:
            return BridgeResult(
                success=False,
                output="",
                exit_code=1,
                error=(
                    "claude CLI not found. Install Claude Code or set "
                    "FLOWSTATE_CLAUDE_BIN to the binary path."
                ),
            )
```
Copy the "`<binary>` not found. Install `<thing>` or set `<ENV_VAR>` to the binary path." phrasing verbatim, substituting the per-platform binary/env-var names (`sandbox-exec`/`FLOWSTATE_SANDBOX_EXEC_BIN` on macOS install hint likely "Xcode Command Line Tools"; `bwrap`/`FLOWSTATE_BWRAP_BIN` on Linux install hint likely the distro package name `bubblewrap`).

### Never-raise vs raise — the one deliberate exception
**Source:** `flowstate/sandbox.py` itself contrasts `check_bwrap_available()` (lines 428-448, catches `OSError`/`TimeoutExpired`, returns `False`, never raises) against `_apply_landlock_syscalls` (lines 333-406, raises `OSError` on any failed syscall — but is immediately caught by its caller `_apply_landlock`, preserving the outer never-raise contract).
**Apply to:** D-01's new raise must be scoped EXACTLY like `_apply_landlock_syscalls`/`_apply_landlock` — a narrow, internal function may raise, but the boundary of what's "loud" vs "swallowed" must be a single, obvious, documented seam (here: `wrap()`'s confine dispatch, or a small helper it calls), not scattered across every degrade site.

### Temp-file cleanup around a subprocess call
**Source:** `bench/replicate.py:_run_trial` (lines 53-92), the only existing codebase precedent for "create temp file → spawn subprocess → guarantee unlink regardless of success/failure."
**Apply to:** `flowstate/bridge.py`'s WR-09 cleanup.
```python
    fd, path = tempfile.mkstemp(prefix=f"repl_{label}_", suffix=".json")
    os.close(fd)
    out = Path(path)
    ...
    try:
        proc = subprocess.run(cmd, check=False)
        ...
    finally:
        out.unlink(missing_ok=True)
```

## No Analog Found

None — every file in scope has at least a role-match analog. The weakest match is the new E2E macOS test file (`tests/test_sandbox_e2e_macos.py`), which has no exact "real-subprocess platform-gated" precedent in the suite; `tests/test_discipline.py`'s binary-presence `skipif` pattern is the best available structural analog and translates cleanly (swap `shutil.which("git") is None` for `sys.platform != "darwin"`).

## Metadata

**Analog search scope:** `flowstate/*.py` (sandbox.py, bridge.py, pack.py, gsd_vendor.py, installer.py, verify.py), `bench/replicate.py`, `tests/*.py` (test_sandbox.py, test_bridge.py, test_discipline.py, test_bench_replicate.py), `.planning/phases/23-linux-parity-core-seam/23-SPIKE-LINUX.md`
**Files scanned:** 12 read in full or targeted ranges; 0 re-reads of overlapping ranges
**Pattern extraction date:** 2026-07-12
