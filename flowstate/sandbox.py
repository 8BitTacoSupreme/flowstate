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
