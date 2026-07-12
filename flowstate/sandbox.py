"""Subprocess confinement seam — env-scrub (`observe`) + platform confinement (`confine`).

Exposes a graceful-degradation seam: importing this module NEVER requires
`bwrap`/Landlock/`sandbox-exec` to be present, and the `observe` tier never
blocks or fails a subprocess call — it is pure env hygiene, not hard
confinement (D-01). `wrap()` never spawns a process itself; it only
transforms `(argv, env)` for the caller to pass to `subprocess.run()`
unchanged (D-04).

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
          executes anything.

Phase 23-01 built the `observe` path and the env-scrub denylist. Plan
23-02 implements the macOS SBPL profile builder (`build_macos_profile`),
its confine wiring (`_wrap_macos`), and the Linux bwrap mount-namespace
argv builder (`build_linux_bwrap_args`) — pure, golden-tested builders,
not yet wired to any live caller (Phase 24) and not yet shipping real
production confinement (Phase 25). Plan 23-03 adds the Landlock ctypes
helper (`_apply_landlock`/`_landlock_available`, import-guarded on
`sys.platform`); `check_bwrap_available`/`_wrap_linux` remain contract
stubs until this plan's second task wires the D-03 degradation ladder.
None of this is wired to a live caller yet (Phase 24/25).
"""

from __future__ import annotations

import ctypes
import os
import platform
import shutil
import struct
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
    """Transform `(cmd, env)` for subprocess confinement. Never spawns a process.

    `surface` is reserved for per-surface policy (Phase 24/25); the
    `observe` tier ignores it. `tier` defaults to `"observe"` — env-scrub
    only, argv untouched, and this call never fails hard regardless of
    platform or tier value.
    """
    scrubbed_env = _scrub_env(env)
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


def build_macos_profile(project_root: Path) -> str:
    """Build the macOS Seatbelt (SBPL) profile string for `project_root`.

    Pure, I/O-free builder — spike-proven shape (23-CONTEXT.md <specifics>):
    `(allow default)` baseline, selective `(deny file-write*)` re-allowing
    `project_root`/`/private/tmp`/`/private/var/folders`/`/dev`, then a
    `(deny file-read* (subpath ~/.ssh))`. Deterministic: two calls with the
    same `project_root` return byte-identical strings.

    T-23-04: `project_root` is embedded verbatim inside a `(subpath "...")`
    quote. This builder is invoked with argv lists, never through a shell,
    so there is no shell-metacharacter surface — but a `project_root`
    containing a literal `"` would still break the profile's SBPL quoting.
    Hardening that edge case is a Phase-25 confine-runtime concern (this
    builder is not wired to a live caller in this phase).
    """
    project = str(project_root)
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
    libc = ctypes.CDLL(None, use_errno=True)

    ruleset_attr = struct.pack(
        "QQ", _LANDLOCK_FULL_ACCESS, 0
    )  # handled_access_fs, handled_access_net
    ruleset_buf = ctypes.create_string_buffer(ruleset_attr, len(ruleset_attr))
    ruleset_fd = libc.syscall(
        _LANDLOCK_NR_CREATE_RULESET, ctypes.byref(ruleset_buf), len(ruleset_attr), 0
    )
    if ruleset_fd < 0:
        return

    def _add_rule(path: Path, access: int) -> None:
        try:
            fd = os.open(str(path), os.O_PATH | os.O_CLOEXEC)
        except OSError:
            return
        try:
            # 16-byte padded struct.landlock_path_beneath_attr (Pitfall 4):
            # the trailing "I" is 4 explicit padding bytes, not real data.
            attr = struct.pack("QiI", access, fd, 0)
            attr_buf = ctypes.create_string_buffer(attr, len(attr))
            libc.syscall(
                _LANDLOCK_NR_ADD_RULE,
                ruleset_fd,
                _LANDLOCK_RULE_PATH_BENEATH,
                ctypes.byref(attr_buf),
                0,
            )
        finally:
            os.close(fd)

    _add_rule(project_root, _LANDLOCK_FULL_ACCESS)
    _add_rule(Path("/tmp"), _LANDLOCK_FULL_ACCESS)
    for system_dir in ("/usr", "/lib", "/bin", "/etc"):
        _add_rule(Path(system_dir), _LANDLOCK_READ_ACCESS)
    _add_rule(
        Path.home() / ".claude", _LANDLOCK_READ_ACCESS
    )  # claude .credentials.json stays readable

    libc.prctl(38, 1, 0, 0, 0)  # PR_SET_NO_NEW_PRIVS, MUST precede restrict_self (Pitfall 5)
    libc.syscall(_LANDLOCK_NR_RESTRICT_SELF, ruleset_fd, 0)
    os.close(ruleset_fd)


def check_bwrap_available() -> bool:
    """Functional smoke test for `bwrap` availability (not a presence check).

    Implemented in plan 23-03.
    """
    raise NotImplementedError("implemented in plan 23-03")  # pragma: no cover


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


def _wrap_linux(
    cmd: list[str], project_root: Path, env: dict[str, str]
) -> tuple[list[str], dict[str, str]]:
    """Prefix `cmd` with `bwrap` + apply landlock rules under Linux confine.

    Implemented in plan 23-03.
    """
    raise NotImplementedError("implemented in plan 23-03")  # pragma: no cover
