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

This phase (23-01) builds ONLY the `observe` path and the env-scrub
denylist. The `confine`-tier platform builders are declared as contract
stubs for plans 23-02 (macOS) and 23-03 (Linux) to implement.
"""

from __future__ import annotations

import sys
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

    Pure, I/O-free builder — implemented in plan 23-02.
    """
    raise NotImplementedError("implemented in plan 23-02/23-03")  # pragma: no cover


def build_linux_bwrap_args(project_root: Path) -> list[str]:
    """Build the `bwrap` argv prefix confining writes to `project_root`.

    Pure, I/O-free builder — implemented in plan 23-03.
    """
    raise NotImplementedError("implemented in plan 23-02/23-03")  # pragma: no cover


def check_bwrap_available() -> bool:
    """Functional smoke test for `bwrap` availability (not a presence check).

    Implemented in plan 23-03.
    """
    raise NotImplementedError("implemented in plan 23-02/23-03")  # pragma: no cover


def _wrap_macos(
    cmd: list[str], project_root: Path, env: dict[str, str]
) -> tuple[list[str], dict[str, str]]:
    """Prefix `cmd` with `sandbox-exec` under the macOS confine profile.

    Implemented in plan 23-02.
    """
    raise NotImplementedError("implemented in plan 23-02/23-03")  # pragma: no cover


def _wrap_linux(
    cmd: list[str], project_root: Path, env: dict[str, str]
) -> tuple[list[str], dict[str, str]]:
    """Prefix `cmd` with `bwrap` + apply landlock rules under Linux confine.

    Implemented in plan 23-03.
    """
    raise NotImplementedError("implemented in plan 23-02/23-03")  # pragma: no cover
