---
phase: 23-linux-parity-core-seam
reviewed: 2026-07-12T00:00:00Z
depth: deep
files_reviewed: 2
files_reviewed_list:
  - flowstate/sandbox.py
  - tests/test_sandbox.py
findings:
  critical: 1
  warning: 9
  info: 3
  total: 13
status: issues_found
---

# Phase 23: Code Review Report

**Reviewed:** 2026-07-12
**Depth:** deep (cross-referenced `flowstate/sandbox.py` against `23-CONTEXT.md`'s locked decisions D-01..D-04, `23-RESEARCH.md`'s verified ctypes/Landlock recipe and pitfalls, and `23-SPIKE-LINUX.md`'s recorded spike methodology)
**Files Reviewed:** 2
**Status:** issues_found

## Summary

`flowstate/sandbox.py` is a security-sensitive OS-confinement seam. The `observe` tier (env-scrub denylist + the `_AUTH_EXEMPT` carve-out) is well-built and well-tested — the auth-carve-out regression tests are present and correct, and D-01's "denylist, not allowlist" contract is honored.

The `confine` tier (macOS `sandbox-exec` builder, Linux `bwrap`+Landlock builder, the ctypes Landlock syscall helper) is where the risk concentrates, and it is the least-tested part of the module. The most serious finding is that the Landlock ctypes helper (`_apply_landlock_syscalls`) never checks the return value of `landlock_restrict_self` (or `landlock_add_rule`): a failed restriction silently returns as if it had succeeded, which is exactly the "false confinement confidence" failure mode this review was asked to weight heavily. Several other findings show that the shipped Linux bwrap-args builder was not actually validated against the same configuration the SBX-01 spike used to declare "PARITY PROVEN" (the spike used a writable `HOME` and the OAuth-token auth path; the shipped builder leaves `HOME`/`~/.claude` entirely read-only and was never tested against the file-based credential path `bridge.py` actually uses). None of this is wired to a live caller yet (Phase 24/25), which is why these are Warnings rather than Blockers in most cases — except the Landlock return-code gap, which is a defect in the mechanism itself regardless of wiring status.

Test coverage is solid for the `observe` tier and the pure golden-tested builders, but the actual security-enforcing code — `_apply_landlock_syscalls`'s syscall sequence and the `__main__` shim that applies Landlock before exec — is entirely `# pragma: no cover` and has no test evidence at all, not even indirect coverage via mocking.

## Critical Issues

### CR-01: `_apply_landlock_syscalls` never checks `landlock_add_rule`/`landlock_restrict_self` return codes — a failed restriction is indistinguishable from a successful one

**File:** `flowstate/sandbox.py:297-342` (specifically `:322-328` and `:340-341`)
**Issue:** `_apply_landlock_syscalls` checks the return value of `landlock_create_ruleset` (`if ruleset_fd < 0: return`, line 309-310) but never checks the return value of `landlock_add_rule` (line 322-328, inside `_add_rule`) or `landlock_restrict_self` (line 341), and never checks `prctl(PR_SET_NO_NEW_PRIVS, ...)` (line 340) either. If `landlock_restrict_self` fails for any reason (a kernel security policy denial, a bad ruleset fd, `prctl` having silently failed one line above, an ABI mismatch not caught by the earlier version probe, etc.), the function proceeds exactly as if the restriction had been applied: it closes `ruleset_fd` and returns normally. `_apply_landlock`'s only safety net is a blanket `except Exception: return` (line 291-294) around the whole call — but a syscall returning a negative errno value via `ctypes`' default `c_int`-guessed return type is **not an exception**, it's a normal return value that is silently discarded.

Concretely: RUNG 1 of `_wrap_linux` (`sandbox.py:454-482`) decides to use the Landlock shim based on `_landlock_available()`'s ABI-version *probe* succeeding — that only proves `landlock_create_ruleset(NULL, 0, VERSION)` works, not that the *actual* ruleset-creation/rule-adding/self-restriction sequence for a specific `project_root` will succeed at runtime. If it silently fails partway through (e.g. `_add_rule` fails for `project_root` because `os.open()` raced with a filesystem change, or `restrict_self` itself is refused), the shim still `execvp`'s the real target command completely **unconfined by Landlock**, with zero warning to the user or caller — unlike the bwrap-unavailable fallback (RUNG 3), which does print a one-time stderr warning. This is exactly the "silently no-op in a way that gives false confinement confidence" failure mode this module's own docstring (`:277-286`) explicitly promises not to have; the promise ("D-03 asymmetric-degrade posture") only covers the case where `_apply_landlock` itself raises, not the case where the underlying syscalls fail quietly.

**Fix:**
```python
def _apply_landlock_syscalls(project_root: Path) -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    ...
    ruleset_fd = libc.syscall(...)
    if ruleset_fd < 0:
        return

    all_ok = True

    def _add_rule(path: Path, access: int) -> None:
        nonlocal all_ok
        try:
            fd = os.open(str(path), os.O_PATH | os.O_CLOEXEC)
        except OSError:
            all_ok = False
            return
        try:
            attr = struct.pack("QiI", access, fd, 0)
            attr_buf = ctypes.create_string_buffer(attr, len(attr))
            rc = libc.syscall(_LANDLOCK_NR_ADD_RULE, ruleset_fd,
                               _LANDLOCK_RULE_PATH_BENEATH, ctypes.byref(attr_buf), 0)
            if rc != 0:
                all_ok = False
        finally:
            os.close(fd)

    _add_rule(project_root, _LANDLOCK_FULL_ACCESS)
    ...

    if libc.prctl(38, 1, 0, 0, 0) != 0:
        all_ok = False
    rc = libc.syscall(_LANDLOCK_NR_RESTRICT_SELF, ruleset_fd, 0)
    os.close(ruleset_fd)
    if rc != 0 or not all_ok:
        # Signal upward so the caller can fall back / warn, mirroring the
        # bwrap-unavailable warning in _wrap_linux rather than silently
        # claiming confinement that never actually applied.
        raise OSError("landlock ruleset application failed")
```
and have `_apply_landlock`'s caller (once wired in Phase 25) treat a raised/failed apply the same way `_wrap_linux` treats bwrap-unavailable — with a visible, one-time degrade warning, not silent success.

## Warnings

### WR-01: `wrap()`'s `tier` parameter is unvalidated — any non-`"observe"` string silently triggers the confine platform-dispatch path

**File:** `flowstate/sandbox.py:142-151`
**Issue:**
```python
scrubbed_env = _scrub_env(env)
if tier == "observe":
    return cmd, scrubbed_env
# tier == "confine" — platform dispatch, profile builders below.
if sys.platform == "darwin":
    return _wrap_macos(cmd, project_root, scrubbed_env)
```
The comment `# tier == "confine"` is aspirational, not enforced — there is no `elif tier == "confine":` check. Any value that isn't the literal string `"observe"` (a typo like `"cofnine"`, `"Confine"`, `"observe "`, or an unrelated string) falls straight into real platform-dispatch/confinement logic. Given the whole point of `observe` being the safe default is that it "must never break a subprocess" (D-01), a caller typo in Phase 24 that produces an unrecognized tier string would silently get real sandboxing behavior instead of the expected safe fallback — the opposite of fail-safe. No test exercises an unrecognized tier value (only `"observe"` and the correctly-spelled `"confine"` are tested).
**Fix:**
```python
if tier not in ("observe", "confine"):
    tier = "observe"  # unknown tier: fail safe to the non-blocking default
if tier == "observe":
    return cmd, scrubbed_env
```
Add a test asserting an unrecognized `tier` value degrades to the observe passthrough.

### WR-02: `build_macos_profile()` embeds `project_root` in SBPL `(subpath "...")` quotes with no escaping — a `"` in the path breaks/injects into the profile

**File:** `flowstate/sandbox.py:159-185`, specifically `:180`
**Issue:** `project = str(project_root)` is interpolated directly into `f'  (subpath "{project}")\n'`. Since `sandbox-exec` parses the resulting `.sb` file as an S-expression, a `project_root` containing a literal `"` terminates the quoted string early and lets the remainder of the path be interpreted as SBPL syntax — at minimum corrupting the profile (breaking confinement, i.e. the profile fails to parse and `sandbox-exec` either errors or falls back to an unintended posture), and at worst allowing a crafted path to inject additional `(allow ...)` clauses. The docstring at `:167-173` already flags this as a known, deferred issue ("Hardening that edge case is a Phase-25 confine-runtime concern") — but it is still a live defect in a function that ships in this phase, and there is currently no regression test locking today's (broken) behavior, so a future accidental "fix" that only partially escapes the string could easily go unnoticed.
**Fix:** Either (a) reject/normalize `project_root` at the `wrap()` boundary before it ever reaches the builder (e.g. require `project_root.resolve()` and reject paths containing `"`), or (b) escape embedded `"` characters when building the SBPL string now rather than deferring to Phase 25, since the builder itself is the natural place to guarantee well-formed output regardless of caller discipline. At minimum, add a test that documents/locks the current behavior (`test_project_root_containing_quote_breaks_profile_TODO_phase25`) so the gap doesn't silently disappear from tracking.

### WR-03: `build_linux_bwrap_args()` leaves `HOME`/`~/.claude` entirely read-only — not the configuration the SBX-01 spike actually validated for auth preservation

**File:** `flowstate/sandbox.py:188-217`
**Issue:** The bwrap argv only makes `project_root` writable (`--bind project project`) and shadows `~/.ssh` with a tmpfs; everything else, including the user's `HOME` (and therefore `~/.claude/.credentials.json`), is covered solely by the blanket `--ro-bind / /`. Cross-referencing `23-SPIKE-LINUX.md` (Task 2, lines 52-70): the spike's auth-preservation probe used **a different configuration** — `--setenv HOME /tmp/chome` (an explicitly writable confined home) — and tested only the OAuth-token env-var auth path (`CLAUDE_CODE_OAUTH_TOKEN`), explicitly noting "This is the **token-path**, not the file-path (`~/.claude/.credentials.json`)... per RESEARCH Open Question #3." The file-based credential path is the one `bridge.py`'s real call site actually uses for the majority of (subscription/interactive-login) users. So the shipped `build_linux_bwrap_args()` has not actually been spike-validated for the auth flow it will be wired to serve, and if `claude` ever needs to write/refresh `~/.claude/.credentials.json` under this exact argv shape, that write will fail with `EROFS`, not silently — but the *risk* SBX-01 was chartered to retire ("preserve `claude` auth and API reachability") is not actually retired for the shipped builder's exact output.
**Fix:** Either explicitly bind `~/.claude` writable (`--bind <home>/.claude <home>/.claude`) in the builder, or re-run/extend the SBX-01 spike specifically against `build_linux_bwrap_args()`'s literal output with the file-based credential path before Phase 25 ships Linux `confine` for real. At minimum, flag this gap in the phase's `VERIFICATION.md`/handoff so Phase 25 doesn't inherit a false sense that auth-preservation is already proven for this exact builder.

### WR-04: Docstrings assert `wrap()`/`_wrap_linux()` never spawn a subprocess (D-04), but `check_bwrap_available()` does — on every confine-tier Linux call

**File:** `flowstate/sandbox.py:6-8` (module docstring), `:448-452` (`_wrap_linux` docstring), `:364-384` (`check_bwrap_available`)
**Issue:** The module docstring states "`wrap()` never spawns a process itself" and `_wrap_linux`'s own docstring repeats "nothing here calls `subprocess.run`, D-04." Both claims are false for the Linux `confine` tier: `_wrap_linux` calls `check_bwrap_available()` (line 454), which runs a real `subprocess.run(["bwrap", "--ro-bind", "/", "/", "--", "/bin/true"], ...)` (lines 377-381) as a functional smoke test. This is the *correct* design per Research Pattern 3 (presence-check alone is insufficient, per the Ubuntu AppArmor pitfall) — the bug is purely in the documentation, but it matters here: D-04 is a **locked** decision that Phase 24/25 implementers will rely on verbatim ("`wrap()` returns a transformed `(argv, env)` tuple; it never executes anything"). A caller who takes that literally (e.g. assuming `wrap()` is side-effect-free, real-time-safe, or safe to call inside another constrained context) will be surprised that every single `confine`-tier Linux invocation spawns an extra, uncached `bwrap ... /bin/true` process as a side effect.
**Fix:** Correct the docstrings to scope the "never spawns" claim precisely (e.g. "never spawns the *target* `cmd`; the Linux confine path does spawn a short-lived `bwrap` availability probe on every call, per Research Pattern 3") so Phase 24/25 callers don't build incorrect assumptions on a locked decision's literal wording. Consider caching `check_bwrap_available()`'s result per-process (it can't change mid-run) to also avoid the repeated spawn.

### WR-05: `_landlock_available()`'s kernel-parsing and ctypes ABI-probe logic is unreachable by the test suite

**File:** `flowstate/sandbox.py:249-274`; `tests/test_sandbox.py:290-295`
**Issue:** The function early-returns `False` at line 261-262 for any non-Linux platform, before the kernel-release parsing (`:263-267`) or the ctypes ABI probe (`:268-272`) ever run. The only test (`TestLandlockAvailable.test_returns_false_on_non_linux_without_raising`) runs on this (Darwin) dev machine and only exercises that early-return branch. None of the following are tested anywhere: a malformed `platform.release()` string, a `(major, minor) < (5, 13)` short-circuit, a `ctypes.CDLL` load failure, or a syscall returning a non-positive version. The `except Exception: return False` clause (line 273-274) — the exact mechanism this security-sensitive probe relies on to fail closed — has zero test evidence that it actually fires correctly for any of its intended failure modes. This is straightforwardly fixable without a real Linux host: `_wrap_linux`'s own tests already monkeypatch `sys.platform`/dependencies to exercise Linux-only branches from Darwin.
**Fix:** Add tests that `monkeypatch.setattr("flowstate.sandbox.sys.platform", "linux")` and then separately mock `platform.release()` (to return a sub-5.13 version, a malformed string, and a valid modern version) and `ctypes.CDLL` (to raise, and to return a mock whose `.syscall(...)` returns 0 / a negative value / a positive version), asserting `_landlock_available()` returns `False`/`True` correctly in each case.

### WR-06: The `__main__` shim — the actual RUNG-1 Landlock-application code path — has zero test coverage

**File:** `flowstate/sandbox.py:485-499`
**Issue:** This block (marked `# pragma: no cover`) is the code that actually runs inside the confined child process on RUNG 1: it parses `--apply-landlock PROJECT_ROOT -- <cmd>`, calls `_apply_landlock`, and `os.execvp`'s the real target. It is the single most security-critical code path in the module — it's what determines whether Landlock is actually applied before the wrapped command executes — yet it has no test coverage at all, not even an indirect one (e.g. invoking `python -m flowstate.sandbox --apply-landlock ... -- true` as a subprocess and asserting exit behavior, which would work cross-platform since `_apply_landlock` itself already no-ops safely on non-Linux). The `argparse.REMAINDER` + manual `"--"`-stripping logic (`:495-496`) is exactly the kind of parsing code that's easy to get subtly wrong (see also IN-03 below) and currently has no regression protection.
**Fix:** Add at least one test that invokes the module's `__main__` entry point (via `subprocess.run([sys.executable, "-m", "flowstate.sandbox", "--apply-landlock", str(tmp_path), "--", sys.executable, "-c", "print('ok')"])`) and asserts it execs the target correctly on any platform (relying on `_apply_landlock`'s no-op-on-non-Linux behavior to make the test portable).

### WR-07: `ctypes` `libc.syscall`/`libc.prctl` calls never declare `argtypes`/`restype` — relies on implicit type coercion for a security-critical syscall wrapper

**File:** `flowstate/sandbox.py:268-272, 306-341`
**Issue:** Every `libc.syscall(...)` and `libc.prctl(...)` call in this module relies on `ctypes`' default argument/return-type guessing rather than declaring `libc.syscall.argtypes`/`.restype` explicitly. `syscall(2)`'s actual C prototype returns `long`, but `ctypes` defaults to `c_int` (32-bit signed) for the return type of an undeclared foreign function. In practice, fd numbers and ABI version numbers returned by these specific syscalls are small enough that 32-bit truncation is unlikely to manifest — but this is exactly the kind of implicit-behavior fragility the project's own "verified ctypes recipe" in `23-RESEARCH.md` inherited from the prior spike without calling out, and it's the sort of thing that silently produces wrong results (a truncated/sign-flipped return value being misread as success or failure) rather than raising, on some future platform/Python/libc combination.
**Fix:** Declare explicit types once, e.g.:
```python
libc.syscall.restype = ctypes.c_long
libc.syscall.argtypes = [ctypes.c_long, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint]
```
(adjusted per call site's actual arg shapes), so the syscall wrapper's behavior no longer depends on ctypes' implicit guessing rules.

### WR-08: `_scrub_env`'s denylist matching is case-sensitive — lower/mixed-case credential-shaped vars silently bypass the scrub

**File:** `flowstate/sandbox.py:99-119`, specifically `:112` (`key.startswith(_DENY_PREFIXES)`) and `:114` (`key.endswith(_DENY_SUFFIXES)`)
**Issue:** All denylist matching (`_DENY_PREFIXES`, `_DENY_SUFFIXES`, `_DENY_EXACT`) is exact-case. Environment variables are conventionally uppercase but not required to be — a subprocess or its own child tooling could set (or a user could export) a lowercase or mixed-case credential-shaped var such as `aws_secret_access_key`, `npm_token`, or `Github_Token`, and it would pass through `_scrub_env` completely untouched, silently defeating the denylist's purpose for that var. This is a narrower case than D-01's explicitly accepted "novel, non-pattern-matching secret" risk (this isn't a *novel* pattern, it's the *same* pattern in different case), and it's cheap to close. No test in `TestScrubEnv` exercises case variation.
**Fix:**
```python
def _scrub_env(env: dict[str, str]) -> dict[str, str]:
    scrubbed: dict[str, str] = {}
    for key, value in env.items():
        if key in _AUTH_EXEMPT:
            scrubbed[key] = value
            continue
        upper_key = key.upper()
        if upper_key.startswith(_DENY_PREFIXES) or upper_key.endswith(_DENY_SUFFIXES) or upper_key in _DENY_EXACT:
            continue
        scrubbed[key] = value
    return scrubbed
```
(Note: exemption check should stay exact-case against `_AUTH_EXEMPT`, since those are FlowState's own known-shape vars, not defeating the fix's intent.)

### WR-09: `_wrap_macos()` leaks a temp `.sb` profile file on every invocation

**File:** `flowstate/sandbox.py:406-420`, specifically `:416-418`
**Issue:** `tempfile.NamedTemporaryFile(mode="w", suffix=".sb", delete=False)` is correct in that `delete=False` is required (the file must outlive this function call so `sandbox-exec -f <path>` can read it during the child's execution) — but nothing anywhere in the module ever removes the file afterward (no caller-side cleanup, no `atexit` hook, no wrapper that unlinks it once the child process this profile was written for has exited). Every `confine`-tier macOS `wrap()` call permanently leaks one `.sb` file into the OS temp directory. This isn't flagged as a performance concern (out of scope) — it's a missing-cleanup correctness gap that will accumulate unboundedly over the life of a long-running or frequently-invoked process once Phase 24/25 wires this tier in.
**Fix:** Since `wrap()` itself can't know when the child process exits (it returns before the caller spawns anything, per D-04), cleanup necessarily belongs to the eventual caller (Phase 24/25) — but that responsibility should be documented explicitly in `_wrap_macos`'s docstring now (e.g. "caller is responsible for unlinking `argv[2]` after the child exits") so it isn't silently forgotten when the live wiring lands.

## Info

### IN-01: `_DENY_EXACT` doesn't cover bare `TOKEN`/`API_KEY`/`SECRET` forms

**File:** `flowstate/sandbox.py:91`
**Issue:** `_DENY_EXACT = frozenset({"SECRET_KEY", "PASSWORD", "PASSWD"})` covers a few bare exact-match secret names but not bare `TOKEN`, `API_KEY`, or `SECRET` — some CI systems set exactly these bare names. Low priority given D-01's explicitly accepted "novel secret shape" risk for the `observe` tier.
**Fix:** Consider adding `"TOKEN"`, `"API_KEY"`, `"SECRET"`, `"CREDENTIALS"` to `_DENY_EXACT` for consistency with the suffix list's vocabulary.

### IN-02: `_bwrap_warning_emitted` module-level global is not thread-safe

**File:** `flowstate/sandbox.py:423`, `:455-462`
**Issue:** The one-time-warning flag is a plain module-level `bool` mutated without any lock. Low risk today given FlowState's single-threaded CLI usage, but worth a note if any concurrent/async caller is ever introduced (the warning could print more than once, or in a worst-case interleaving, theoretically never — though the latter is very unlikely with GIL semantics for this simple read-then-write).
**Fix:** No action needed now; flagging for awareness only.

### IN-03: `__main__` shim's `os.execvp(remainder[0], remainder)` can raise uncaught if malformed

**File:** `flowstate/sandbox.py:495-499`
**Issue:** If `args.child_cmd` is empty or doesn't contain a valid command after `"--"`-stripping, `remainder` could be `[]`, and `remainder[0]` raises an uncaught `IndexError`. If `remainder[0]` isn't an executable that exists, `os.execvp` raises an uncaught `OSError`/`FileNotFoundError`. Since this only runs inside the spawned confined child (not the parent FlowState process) and is never reachable via any wired caller in this phase, severity is low — but worth a defensive check once Phase 25 wires this shim into a real launch path, so a malformed invocation fails with a clear message rather than a raw traceback.
**Fix:** Add a guard: `if not remainder: sys.exit("flowstate.sandbox: no target command given")` before the `execvp` call.

---

_Reviewed: 2026-07-12_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: deep_
