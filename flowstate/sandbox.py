"""Subprocess confinement seam — env-scrub (`observe`) + platform confinement (`confine`).

Exposes a graceful-degradation seam: importing this module NEVER requires
`bwrap`/Landlock/`sandbox-exec` to be present, and the `observe` tier never
blocks or fails a subprocess call — it is pure env hygiene, not hard
confinement (D-01). `wrap()` never spawns the *target* `cmd` itself; it
transforms `(argv, env)` for the caller to pass to `subprocess.run()`
unchanged (D-04). WR-04: this does NOT mean `wrap()` is side-effect-free on
every path — the Linux `confine` tier's `check_bwrap_available()` runs a
real, short-lived `bwrap ... /bin/true` availability probe on every call
(Research Pattern 3); that probe subprocess is not the target `cmd`, but
callers should not assume `wrap()` never spawns anything at all.

Public API::

    from flowstate.sandbox import wrap

    cmd, env = wrap(["claude", "--print", "..."], "llm", project_root, os.environ.copy())
    subprocess.run(cmd, env=env, ...)

Decision cross-references (see .planning/phases/23-linux-parity-core-seam/23-CONTEXT.md):
    D-01: `observe` tier strips known-secret patterns (denylist), passes
          everything else through — never breaks a subprocess.
    D-02: Linux `confine` layers landlock LSM rules on top of a bwrap mount
          namespace (implemented in plans 23-02/23-03, stubbed here).
    D-03: Asymmetric degrade — a failed Linux confinement path falls back
          to a warned observe-only posture rather than blocking the tier
          (implemented in plans 23-02/23-03).
    D-04: `wrap()` returns a transformed `(argv, env)` tuple; it never
          executes the target `cmd` itself (though the Linux confine path's
          `check_bwrap_available()` availability probe does spawn a
          short-lived `bwrap ... /bin/true` smoke-test subprocess — WR-04).

Phase 23-01 built the `observe` path and the env-scrub denylist. Plan
23-02 implements the macOS SBPL profile builder (`build_macos_profile`),
its confine wiring (`_wrap_macos`), and the Linux bwrap mount-namespace
argv builder (`build_linux_bwrap_args`) — pure, golden-tested builders,
not yet wired to any live caller (Phase 24) and not yet shipping real
production confinement (Phase 25). Plan 23-03 completes the Linux path:
the Landlock ctypes helper (`_apply_landlock`/`_landlock_available`), the
functional `check_bwrap_available` smoke test, and `_wrap_linux`'s D-03
two-rung degradation ladder (bwrap+landlock -> bwrap-only -> observe).
None of this is wired to a live caller yet (Phase 24/25).
"""

from __future__ import annotations

import ctypes
import os
import platform
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

# ---------------------------------------------------------------------------
# Env-scrub denylist (D-01) — see 23-RESEARCH.md Pitfall 1 for the auth
# carve-out rationale. Deliberately does NOT include a bare "ANTHROPIC_"
# prefix (unlike the sandflox reference) because FlowState's own `claude`
# auth lives there — a bare-prefix block would break the very subprocess
# `observe` exists to protect.
# ---------------------------------------------------------------------------

_DENY_PREFIXES = (
    "AWS_",
    "AZURE_",
    "GCP_",
    "GCLOUD_",
    "SSH_",
    "GPG_",
    "DOCKER_",
    "KUBE",
    "GITHUB_",
    "GITLAB_",
    "BITBUCKET_",
    "STRIPE_",
    "TWILIO_",
    "SENDGRID_",
    "SLACK_",
    "DISCORD_",
    "DATABASE_",
    "DB_",
    "REDIS_",
    "MONGO",
)

_DENY_SUFFIXES = (
    "_API_KEY",
    "_TOKEN",
    "_SECRET",
    "_PASSWORD",
    "_CREDENTIALS",
)

_DENY_EXACT = frozenset({"SECRET_KEY", "PASSWORD", "PASSWD"})

# Auth-carve-out (23-RESEARCH.md Pitfall 1): these names are FlowState's own
# `claude` headless-auth mechanism, not a leaked third-party secret. Checked
# BEFORE any denylist match so they always survive the scrub.
_AUTH_EXEMPT = frozenset({"ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN", "CLAUDE_CONFIG_DIR"})


def _scrub_env(env: dict[str, str]) -> dict[str, str]:
    """Return a new env dict with credential-shaped vars removed.

    Denylist, not allowlist (D-01): unmatched vars pass through untouched so
    a scrubbed environment never starves a subprocess (`git`/`npx`/`repomix`)
    of vars it legitimately needs. `_AUTH_EXEMPT` names always survive,
    checked before any prefix/suffix/exact match. Never mutates `env`.
    """
    scrubbed: dict[str, str] = {}
    for key, value in env.items():
        if key in _AUTH_EXEMPT:
            scrubbed[key] = value
            continue
        if key.startswith(_DENY_PREFIXES):
            continue
        if key.endswith(_DENY_SUFFIXES):
            continue
        if key in _DENY_EXACT:
            continue
        scrubbed[key] = value
    return scrubbed


# ---------------------------------------------------------------------------
# wrap() seam (D-04)
# ---------------------------------------------------------------------------


def wrap(
    cmd: list[str],
    surface: str,
    project_root: Path,
    env: dict[str, str],
    *,
    tier: str = "observe",
) -> tuple[list[str], dict[str, str]]:
    """Transform `(cmd, env)` for subprocess confinement.

    Never spawns the target `cmd`. WR-04: the Linux `confine` tier does
    spawn a short-lived `bwrap ... /bin/true` availability-probe subprocess
    on every call (see module docstring / `check_bwrap_available()`) — that
    probe is not the target `cmd`, but this call is not perfectly
    side-effect-free on that one path.

    `surface` is reserved for per-surface policy (Phase 24/25); the
    `observe` tier ignores it. `tier` defaults to `"observe"` — env-scrub
    only, argv untouched, and this call never fails hard regardless of
    platform or tier value.
    """
    scrubbed_env = _scrub_env(env)
    if tier not in ("observe", "confine"):
        tier = "observe"  # WR-01: unknown tier value fails safe to the non-blocking default
    if tier == "observe":
        return cmd, scrubbed_env
    # tier == "confine" — platform dispatch, profile builders below.
    if sys.platform == "darwin":
        return _wrap_macos(cmd, project_root, scrubbed_env)
    if sys.platform.startswith("linux"):
        return _wrap_linux(cmd, project_root, scrubbed_env)
    # Unsupported platform: env-scrub only, never hard-fail (D-03 posture).
    return cmd, scrubbed_env


# ---------------------------------------------------------------------------
# Confine-path contract stubs (implemented in plans 23-02/23-03)
# ---------------------------------------------------------------------------


def _escape_sbpl_string(raw: str) -> str:
    """Escape `raw` for safe embedding inside an SBPL double-quoted string.

    WR-02: SBPL is parsed as an S-expression; a literal `"` in an
    interpolated value would terminate the quoted string early and let the
    remainder be interpreted as SBPL syntax (profile corruption at best,
    injected `(allow ...)` clauses at worst). Escapes backslashes first
    (so an escaped backslash isn't re-escaped by the quote pass), then
    double quotes.
    """
    return raw.replace("\\", "\\\\").replace('"', '\\"')


def build_macos_profile(project_root: Path) -> str:
    """Build the macOS Seatbelt (SBPL) profile string for `project_root`.

    Pure, I/O-free builder — spike-proven shape (23-CONTEXT.md <specifics>):
    `(allow default)` baseline, selective `(deny file-write*)` re-allowing
    `project_root`/`/private/tmp`/`/private/var/folders`/`/dev`, then a
    `(deny file-read* (subpath ~/.ssh))`. Deterministic: two calls with the
    same `project_root` return byte-identical strings.

    T-23-04 / WR-02: `project_root` is embedded inside a `(subpath "...")`
    quote via `_escape_sbpl_string`, so a literal `"` or `\\` in the path no
    longer breaks or injects into the generated profile. This builder is
    invoked with argv lists, never through a shell, so there is no
    shell-metacharacter surface separately from this SBPL-quoting concern.
    """
    project = _escape_sbpl_string(str(project_root))
    return f"""(version 1)
(allow default)
(deny file-write*)
(allow file-write*
  (subpath "{project}")
  (subpath "/private/tmp")
  (subpath "/private/var/folders")
  (subpath "/dev"))
(deny file-read* (subpath "{Path.home() / ".ssh"}"))
"""


def build_linux_bwrap_args(project_root: Path) -> list[str]:
    """Build the `bwrap` mount-namespace argv confining writes to `project_root`.

    Pure, I/O-free builder — no subprocess, no ctypes, no file I/O inside
    this function. Returns ARGS ONLY: no `bwrap` binary, no `--` separator,
    no target cmd. `_wrap_linux` (plan 23-03) prepends the located `bwrap`
    binary and appends `["--", *cmd]`. The `--tmpfs <home>/.ssh` shadows the
    ssh dir (Information-Disclosure mitigation, 23-RESEARCH.md Security
    Domain). Deterministic: two calls with the same `project_root` return an
    equal list.
    """
    project = str(project_root)
    return [
        "--ro-bind",
        "/",
        "/",
        "--bind",
        project,
        project,
        "--tmpfs",
        str(Path.home() / ".ssh"),
        "--dev",
        "/dev",
        "--proc",
        "/proc",
        "--unshare-pid",
        "--unshare-uts",
        "--unshare-ipc",
        "--die-with-parent",
    ]


# ---------------------------------------------------------------------------
# Landlock LSM ctypes helper (D-02 defense-in-depth, Linux-only)
#
# LOCKED implementation choice (RESEARCH.md "Don't Hand-Roll" + D-02/D-04):
# raw ctypes syscalls, not the `py-landlock`/`landlock` PyPI packages. Both
# were evaluated and REJECTED — they'd add a third-party dependency for ~3
# raw syscalls FlowState can implement in-tree (already proven working in
# the prior spike), violating the project's no-new-core-runtime-dependency
# rule. A reviewer must NOT "fix" this by importing `py-landlock` — that is
# the wrong direction for this specific, deliberately-inverted case.
# ---------------------------------------------------------------------------

# Landlock syscall numbers — identical on x86_64 and arm64 (both use the
# generic 64-bit syscall table; verified against kernel patchwork + syscall
# reference tables, 23-RESEARCH.md).
_LANDLOCK_NR_CREATE_RULESET = 444
_LANDLOCK_NR_ADD_RULE = 445
_LANDLOCK_NR_RESTRICT_SELF = 446

_LANDLOCK_RULE_PATH_BENEATH = 1
_LANDLOCK_CREATE_RULESET_VERSION = 1  # flags value: query ABI version, don't create

_LANDLOCK_READ_ACCESS = (1 << 0) | (1 << 2) | (1 << 3)  # EXECUTE | READ_FILE | READ_DIR
_LANDLOCK_WRITE_ACCESS = (
    (1 << 1) | (1 << 4) | (1 << 5) | (1 << 8)
)  # WRITE_FILE | REMOVE_DIR/FILE | MAKE_REG
_LANDLOCK_FULL_ACCESS = _LANDLOCK_READ_ACCESS | _LANDLOCK_WRITE_ACCESS


def _landlock_available() -> bool:
    """Best-effort Landlock LSM availability probe. Never raises.

    Kernel-version-only gating is insufficient (23-RESEARCH.md Anti-Patterns):
    gates on `platform.release()` >= 5.13 (Landlock's minimum kernel) AND a
    live `landlock_create_ruleset(NULL, 0, LANDLOCK_CREATE_RULESET_VERSION)`
    version probe returning a positive ABI version. Mirrors
    `flowstate/embeddings.py`'s cached-unavailable-sentinel, never-raise
    degradation shape. Returns False (not an exception) for any failure:
    non-Linux platform, unparseable kernel release string, or a syscall
    error.
    """
    if not sys.platform.startswith("linux"):
        return False
    try:
        release_parts = platform.release().split(".")[:2]
        major, minor = (int(part) for part in release_parts)
        if (major, minor) < (5, 13):
            return False
        libc = ctypes.CDLL(None, use_errno=True)
        version = libc.syscall(
            _LANDLOCK_NR_CREATE_RULESET, None, 0, _LANDLOCK_CREATE_RULESET_VERSION
        )
        return version > 0
    except Exception:
        return False


def _apply_landlock(project_root: Path) -> None:
    """Apply a Landlock path-beneath ruleset to the current process.

    No-op on any non-Linux platform (guarded first, before any ctypes
    touches occur). On Linux, restricts writes to `project_root` and `/tmp`,
    and reads to the core system dirs plus `~/.claude` (so `claude`'s
    `.credentials.json` stays readable — RESEARCH.md's Linux auth model);
    `~/.ssh` gets no read rule at all (default-deny, T-23-10). Never raises
    — a failed apply leaves the process unconfined-by-Landlock rather than
    crashing it (D-03 asymmetric-degrade posture); the bwrap mount namespace
    layer (23-02) still applies independently.
    """
    if not sys.platform.startswith("linux"):
        return
    try:
        _apply_landlock_syscalls(project_root)
    except Exception:
        return


def _apply_landlock_syscalls(
    project_root: Path,
) -> None:  # pragma: no cover -- Linux-only; behavior-verified against the SBX-01 spike (plan 23-04), not exercised on this Darwin dev machine
    """Apply the Landlock ruleset via raw syscalls. Raises `OSError` on any failure.

    CR-01: every syscall return code is checked. A failed `landlock_add_rule`,
    a failed `prctl(PR_SET_NO_NEW_PRIVS)`, or a failed `landlock_restrict_self`
    now raises instead of silently returning as if confinement had applied —
    a `landlock_restrict_self` return value is a normal `c_long`, not a Python
    exception, so it must be checked explicitly rather than relying on
    `_apply_landlock`'s `except Exception` to catch it. `_apply_landlock`
    (the caller) still catches this and no-ops, per D-03 asymmetric-degrade
    posture — this function's job is only to make failure *observable*
    (raise), not to decide how the caller degrades.
    """
    libc = ctypes.CDLL(None, use_errno=True)

    ruleset_attr = struct.pack(
        "QQ", _LANDLOCK_FULL_ACCESS, 0
    )  # handled_access_fs, handled_access_net
    ruleset_buf = ctypes.create_string_buffer(ruleset_attr, len(ruleset_attr))
    ruleset_fd = libc.syscall(
        _LANDLOCK_NR_CREATE_RULESET, ctypes.byref(ruleset_buf), len(ruleset_attr), 0
    )
    if ruleset_fd < 0:
        raise OSError("landlock_create_ruleset failed")

    all_ok = True

    def _add_rule(path: Path, access: int) -> None:
        nonlocal all_ok
        try:
            fd = os.open(str(path), os.O_PATH | os.O_CLOEXEC)
        except OSError:
            all_ok = False
            return
        try:
            # 16-byte padded struct.landlock_path_beneath_attr (Pitfall 4):
            # the trailing "I" is 4 explicit padding bytes, not real data.
            attr = struct.pack("QiI", access, fd, 0)
            attr_buf = ctypes.create_string_buffer(attr, len(attr))
            rc = libc.syscall(
                _LANDLOCK_NR_ADD_RULE,
                ruleset_fd,
                _LANDLOCK_RULE_PATH_BENEATH,
                ctypes.byref(attr_buf),
                0,
            )
            if rc != 0:
                all_ok = False
        finally:
            os.close(fd)

    _add_rule(project_root, _LANDLOCK_FULL_ACCESS)
    _add_rule(Path("/tmp"), _LANDLOCK_FULL_ACCESS)
    for system_dir in ("/usr", "/lib", "/bin", "/etc"):
        _add_rule(Path(system_dir), _LANDLOCK_READ_ACCESS)
    _add_rule(
        Path.home() / ".claude", _LANDLOCK_READ_ACCESS
    )  # claude .credentials.json stays readable

    # PR_SET_NO_NEW_PRIVS, MUST precede restrict_self (Pitfall 5)
    if libc.prctl(38, 1, 0, 0, 0) != 0:
        all_ok = False
    rc = libc.syscall(_LANDLOCK_NR_RESTRICT_SELF, ruleset_fd, 0)
    os.close(ruleset_fd)
    if rc != 0 or not all_ok:
        raise OSError("landlock ruleset application failed — restriction was not fully applied")


def _find_bwrap() -> str:
    """Locate the `bwrap` binary.

    Resolution order (mirrors `flowstate/pack.py:_find_repomix`):
    1. `FLOWSTATE_BWRAP_BIN` env var (must point to an existing file)
    2. `shutil.which("bwrap")` (PATH search)
    3. `""` — not found; `check_bwrap_available()` already gates on this.
    """
    env_path = os.environ.get("FLOWSTATE_BWRAP_BIN")
    if env_path and Path(env_path).is_file():
        return env_path

    found = shutil.which("bwrap")
    if found:
        return found

    return ""


def check_bwrap_available() -> bool:
    """Functional smoke test for `bwrap` availability (not a presence check).

    T-23-08: `shutil.which("bwrap")` alone is insufficient — a modern
    Ubuntu 24.04+ host can have `bwrap` on PATH yet fail via AppArmor's
    `apparmor_restrict_unprivileged_userns=1` (23-RESEARCH.md Pitfall 3).
    Runs a real `bwrap --ro-bind / / -- /bin/true` invocation and checks its
    exit code; never raises (OSError / TimeoutExpired both degrade to
    False).
    """
    if shutil.which("bwrap") is None:
        return False
    try:
        result = subprocess.run(
            ["bwrap", "--ro-bind", "/", "/", "--", "/bin/true"],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _find_sandbox_exec() -> str:
    """Locate the `sandbox-exec` binary.

    Resolution order (mirrors `flowstate/pack.py:_find_repomix`):
    1. `FLOWSTATE_SANDBOX_EXEC_BIN` env var (must point to an existing file)
    2. `shutil.which("sandbox-exec")` (PATH search)
    3. Fallback `/usr/bin/sandbox-exec`
    """
    env_path = os.environ.get("FLOWSTATE_SANDBOX_EXEC_BIN")
    if env_path and Path(env_path).is_file():
        return env_path

    found = shutil.which("sandbox-exec")
    if found:
        return found

    return "/usr/bin/sandbox-exec"


def _wrap_macos(
    cmd: list[str], project_root: Path, env: dict[str, str]
) -> tuple[list[str], dict[str, str]]:
    """Prefix `cmd` with `sandbox-exec` under the macOS confine profile.

    Writes `build_macos_profile(project_root)` to a temp `.sb` file
    (`sandbox-exec` requires a file path, not stdin) and prefixes argv with
    `sandbox-exec -f <profile-path>`. `env` is passed through unchanged.
    """
    profile = build_macos_profile(project_root)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".sb", delete=False) as f:
        f.write(profile)
        profile_path = f.name
    sbx = _find_sandbox_exec()
    return [sbx, "-f", profile_path, *cmd], env


_bwrap_warning_emitted = False


def _wrap_linux(
    cmd: list[str], project_root: Path, env: dict[str, str]
) -> tuple[list[str], dict[str, str]]:
    """Prefix `cmd` with `bwrap` (+ a Landlock-applying shim) under Linux confine.

    Implements exactly D-03's TWO-rung degradation ladder:
      RUNG 1 (bwrap + landlock): `check_bwrap_available()` True AND
        `_landlock_available()` True -> bwrap-prefixed argv whose target is
        a self-invoking `python -m flowstate.sandbox --apply-landlock ...`
        shim that applies `_apply_landlock` before exec-ing `cmd`.
      RUNG 2 (bwrap-only): `check_bwrap_available()` True, landlock
        unavailable -> bwrap-prefixed argv, `cmd` unchanged as the target.
      RUNG 3 (observe fallback): `check_bwrap_available()` False -> `cmd`
        and `env` returned unchanged, with a one-time stderr warning.

    REJECTED rung (23-RESEARCH.md Open Question #1 / D-03): a Landlock-only
    rung (bwrap absent, landlock present — FS enforcement with no namespace
    isolation) is deliberately NOT implemented. D-03's wording names exactly
    two fallback rungs; the invented Landlock-only rung is a documented
    future refinement, not silently added here. bwrap-absent always
    collapses straight to RUNG 3 (observe), never to a bare-landlock rung.

    Phase 23 builds and golden-tests the argv SHAPE only — the shim actually
    executing `_apply_landlock` before the real target process spawns is
    exercised by the caller's `subprocess.run()` (Phase 25 wires the live
    spawn path; nothing here calls `subprocess.run()` on the TARGET `cmd`,
    D-04). WR-04: `check_bwrap_available()` (called by this function on
    every invocation) DOES spawn a short-lived `bwrap ... /bin/true`
    availability-probe subprocess — that's a probe, not the target `cmd`,
    but it means this function is not literally subprocess-free. Never
    raises regardless of which rung fires (T-23-11).
    """
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

    bwrap_prefix = [_find_bwrap(), *build_linux_bwrap_args(project_root), "--"]

    if _landlock_available():
        # RUNG 1: bwrap + landlock shim.
        target = [
            sys.executable,
            "-m",
            "flowstate.sandbox",
            "--apply-landlock",
            str(project_root),
            "--",
            *cmd,
        ]
    else:
        # RUNG 2: bwrap-only.
        target = list(cmd)

    return bwrap_prefix + target, env


if (
    __name__ == "__main__"
):  # pragma: no cover -- exercised only inside the confined child; live spawn wiring is Phase 25
    import argparse

    parser = argparse.ArgumentParser(prog="python -m flowstate.sandbox")
    parser.add_argument("--apply-landlock", required=True, metavar="PROJECT_ROOT")
    parser.add_argument("child_cmd", nargs=argparse.REMAINDER)
    args = parser.parse_args()

    remainder = (
        args.child_cmd[1:] if args.child_cmd and args.child_cmd[0] == "--" else args.child_cmd
    )
    _apply_landlock(Path(args.apply_landlock))
    os.execvp(remainder[0], remainder)
