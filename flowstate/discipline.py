"""Discipline module — pure Python project audit (replaces superpowers.py).

Checks git repo health, test configuration, and hooks without any LLM calls.
On a LIVE run it also runs the project's test suite (a GATING check), reads
real git state (branch / dirty / ahead-behind), and inspects hook CONTENTS.
Under --dry-run it stays side-effect-free: zero subprocess spawns, tests are
reported-only, mirroring the other adapters' MOCK paths.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

# 15 min — generous so a healthy real suite is never spuriously failed; a
# timeout still degrades to None -> audit fails (honest fail, never a hang).
_TEST_TIMEOUT = 900
_GIT_TIMEOUT = 30
_REQUIRED_LIVE = ("git_repo", "pytest_config", "tests_pass")
_REQUIRED_DRYRUN = ("git_repo", "pytest_config")


@dataclass
class AuditResult:
    success: bool
    checks: dict[str, bool] = field(default_factory=dict)
    summary: str = ""
    required: tuple[str, ...] = _REQUIRED_LIVE


def _read_git_state(root: Path) -> dict:
    """Read real git state: branch, dirty flag, ahead/behind counts.

    Pure subprocess with argv LISTs (never a shell string). Any failure —
    missing git binary, not a repo, no upstream — degrades to None/False safe
    defaults and never raises. Branch names and paths are inert argv elements,
    so a malicious branch name cannot inject a command.

    SBX-03/D-01: these three subprocess.run calls (and _run_project_tests'
    pytest call below) are DELIBERATELY left un-wrapped by flowstate.sandbox's
    wrap(). They are internal, read-only `git` commands with no agent-directed
    or untrusted input and no injection surface — confining a read-only
    `git status` buys nothing, and scrubbing GIT_* env off them could only
    risk breaking them. This is a decision, not an omission: the SBX-03 site
    inventory (plan 24-02) accounts for these four sites explicitly. A `vcs`
    confine profile is reserved for Phase 25 only if a real threat surfaces.
    """
    state: dict = {"branch": None, "dirty": None, "ahead": None, "behind": None}
    try:
        branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT,
        )
        if branch.returncode == 0:
            state["branch"] = branch.stdout.strip() or None

        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT,
        )
        if status.returncode == 0:
            state["dirty"] = bool(status.stdout.strip())

        counts = subprocess.run(
            ["git", "rev-list", "--left-right", "--count", "@{u}...HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT,
        )
        if counts.returncode == 0:
            parts = counts.stdout.split()
            if len(parts) == 2:
                # `--left-right` with `@{u}...HEAD`: left=@{u} (behind), right=HEAD (ahead).
                try:
                    state["behind"] = int(parts[0])
                    state["ahead"] = int(parts[1])
                except ValueError:
                    pass
    except (FileNotFoundError, subprocess.TimeoutExpired, subprocess.CalledProcessError):
        pass
    return state


def _run_project_tests(root: Path) -> bool | None:
    """Run the project's test suite as a gating check.

    True on returncode 0; False on any other returncode (incl. pytest exit 5,
    "no tests collected"); None only when the runner cannot be invoked
    (FileNotFoundError) or times out. Bounded by _TEST_TIMEOUT; never raises.
    """
    try:
        # SBX-03/D-01: internal read-only command, deliberately left un-wrapped
        # — see _read_git_state.
        result = subprocess.run(
            ["python", "-m", "pytest", "-q"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=_TEST_TIMEOUT,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    return result.returncode == 0


def _check_hook_contents(root: Path) -> bool:
    """Pre-commit hook is present, non-empty, and executable. NEVER executes it."""
    hook = root / ".git" / "hooks" / "pre-commit"
    return hook.is_file() and hook.stat().st_size > 0 and os.access(hook, os.X_OK)


def check_setup(root: Path, *, dry_run: bool = False) -> AuditResult:
    """Audit git repo, test config, and hooks. Pure Python, no LLM.

    On a LIVE run this GATES on a passing test suite and reads real git state;
    under dry_run it spawns ZERO subprocesses and reports tests/git as skipped.
    """
    checks: dict[str, bool] = {}

    # Git repo
    checks["git_repo"] = (root / ".git").is_dir()

    # Test config
    checks["pytest_config"] = (
        (root / "pyproject.toml").exists()
        or (root / "pytest.ini").exists()
        or (root / "setup.cfg").exists()
    )

    # Pre-commit hooks
    checks["pre_commit_config"] = (root / ".pre-commit-config.yaml").exists()
    # Contents, not mere presence: non-empty + executable (no subprocess spawn).
    checks["git_hooks"] = _check_hook_contents(root)

    # Directory structure
    checks["tests_dir"] = (root / "tests").is_dir()
    checks["src_dir"] = (root / "src").is_dir() or _has_python_package(root)

    # Planning artifacts
    checks["planning_dir"] = (root / ".planning").is_dir()

    extra_lines: list[str] = []

    if dry_run:
        # Side-effect-free: no pytest / git spawns. tests_pass is reported-only
        # (present in checks for shape, but NOT in the required-set).
        checks["tests_pass"] = False
        required = _REQUIRED_DRYRUN
        extra_lines.append("  Git state: skipped (dry-run)")
        extra_lines.append("  Tests: skipped (dry-run)")
    else:
        git_state = _read_git_state(root)
        tests_result = _run_project_tests(root)
        checks["tests_pass"] = tests_result is True
        required = _REQUIRED_LIVE

        branch = git_state["branch"] or "unknown"
        if git_state["dirty"] is None:
            dirty = "unknown"
        else:
            dirty = "dirty" if git_state["dirty"] else "clean"
        extra_lines.append(f"  Git state: branch {branch}, {dirty}")
        if git_state["ahead"] is not None and git_state["behind"] is not None:
            extra_lines.append(
                f"  Upstream: ahead {git_state['ahead']}, behind {git_state['behind']}"
            )
        else:
            extra_lines.append("  Upstream: none")
        if tests_result is True:
            test_line = "passed"
        elif tests_result is False:
            test_line = "failed"
        else:
            test_line = "not run"
        extra_lines.append(f"  Tests: {test_line}")

    passed = sum(1 for v in checks.values() if v)
    total = len(checks)

    lines = []
    for check, ok in checks.items():
        marker = "+" if ok else "-"
        label = check.replace("_", " ").title()
        lines.append(f"  [{marker}] {label}")

    summary = f"Audit: {passed}/{total} checks passed\n" + "\n".join(lines)
    if extra_lines:
        summary += "\n" + "\n".join(extra_lines)

    # Required-set: the floor for "healthy enough to proceed." On live runs a
    # passing test suite (tests_pass) is a GATING member — a failing OR absent
    # suite fails the audit. The other checks are informational (reported in
    # summary, never gating success).
    success = all(checks[key] for key in required)

    return AuditResult(
        success=success,
        checks=checks,
        summary=summary,
        required=required,
    )


def _has_python_package(root: Path) -> bool:
    """Check if root contains a Python package (dir with __init__.py)."""
    return any(child.is_dir() and (child / "__init__.py").exists() for child in root.iterdir())
