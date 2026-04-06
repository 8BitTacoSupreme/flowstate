"""Discipline module — pure Python project audit (replaces superpowers.py).

Checks git repo health, test configuration, and hooks without any LLM calls.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class AuditResult:
    success: bool
    checks: dict[str, bool] = field(default_factory=dict)
    summary: str = ""


def check_setup(root: Path) -> AuditResult:
    """Audit git repo, test config, and hooks. Pure Python, no LLM."""
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
    checks["git_hooks"] = (root / ".git" / "hooks" / "pre-commit").exists()

    # Directory structure
    checks["tests_dir"] = (root / "tests").is_dir()
    checks["src_dir"] = (root / "src").is_dir() or _has_python_package(root)

    # Planning artifacts
    checks["planning_dir"] = (root / ".planning").is_dir()

    passed = sum(1 for v in checks.values() if v)
    total = len(checks)

    lines = []
    for check, ok in checks.items():
        marker = "+" if ok else "-"
        label = check.replace("_", " ").title()
        lines.append(f"  [{marker}] {label}")

    summary = f"Audit: {passed}/{total} checks passed\n" + "\n".join(lines)

    return AuditResult(
        success=True,
        checks=checks,
        summary=summary,
    )


def check_superpowers_installed() -> bool:
    """Check if the Superpowers plugin is installed."""
    plugin_dir = Path.home() / ".claude" / "plugins" / "superpowers"
    return plugin_dir.exists()


def _has_python_package(root: Path) -> bool:
    """Check if root contains a Python package (dir with __init__.py)."""
    for child in root.iterdir():
        if child.is_dir() and (child / "__init__.py").exists():
            return True
    return False
