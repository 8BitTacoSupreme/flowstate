"""Superpowers adapter — disciplined execution with worktree management."""

from __future__ import annotations

from pathlib import Path

from flowstate.state import InterviewAnswers
from flowstate.tools.base import ToolAdapter, ToolResult


class SuperpowersAdapter(ToolAdapter):
    name = "superpowers"

    def init_repo(self, answers: InterviewAnswers) -> ToolResult:
        if self.dry_run:
            return ToolResult(
                success=True,
                output=(
                    f"[dry-run] Would execute: superpowers /init-repo\n"
                    f"  - Test coverage target: {answers.test_coverage}%\n"
                    f"  - Architecture: {answers.architecture_pattern or 'default'}\n"
                    f"  - Git hooks: pre-commit, pre-push\n"
                    f"  - Worktree branching: enabled"
                ),
                artifacts=[],
            )

        return self.run_cmd([
            "superpowers", "/init-repo",
            "--coverage", str(answers.test_coverage),
            "--pattern", answers.architecture_pattern or "layered",
        ])

    def should_branch(self, phase_label: str) -> bool:
        """Detect if a feature is past MVP and should use a worktree branch."""
        hardening_keywords = {"harden", "stabilize", "polish", "optimize", "scale"}
        return any(kw in phase_label.lower() for kw in hardening_keywords)
