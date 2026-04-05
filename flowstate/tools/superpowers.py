"""Superpowers adapter — disciplined execution with worktree management.

Live mode uses the claude CLI to set up git hooks, coding standards,
and the worktree-based branching strategy. Also manages the TDD loop
for disciplined implementation.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from textwrap import dedent

from flowstate.state import InterviewAnswers
from flowstate.tools.base import ToolAdapter, ToolResult

INIT_SYSTEM_PROMPT = dedent("""\
    You are a senior software engineer setting up a disciplined development
    environment. Your job is to configure:
    1. Git hooks (pre-commit for linting, pre-push for tests)
    2. Test infrastructure matching the project's language/framework
    3. Code coverage configuration at the specified target
    4. Architecture scaffolding following the specified pattern

    Execute commands directly. Do not ask questions.
    Output a summary of what was configured.
""").strip()


def _build_init_prompt(answers: InterviewAnswers) -> str:
    return dedent(f"""\
        Set up a disciplined development environment:

        - Test coverage target: {answers.test_coverage}%
        - Architecture pattern: {answers.architecture_pattern or 'layered'}
        - Initialize git repo if not already initialized
        - Set up pre-commit hooks for code quality
        - Configure test runner and coverage reporting
        - Create initial directory structure following the architecture pattern

        Output a summary of what you configured.
    """)


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
            )

        prompt = _build_init_prompt(answers)
        br = self.bridge.run(
            prompt,
            system_prompt=INIT_SYSTEM_PROMPT,
            allowed_tools=["Bash", "Write", "Edit", "Read", "Glob"],
            max_turns=20,
        )

        return self.bridge_to_result(br)

    def should_branch(self, phase_label: str) -> bool:
        """Detect if a feature is past MVP and should use a worktree branch."""
        hardening_keywords = {"harden", "stabilize", "polish", "optimize", "scale"}
        return any(kw in phase_label.lower() for kw in hardening_keywords)

    def create_worktree(self, branch_name: str) -> ToolResult:
        """Create a git worktree for isolated feature work."""
        if self.dry_run:
            return ToolResult(
                success=True,
                output=f"[dry-run] Would create worktree: {branch_name}",
            )

        worktree_path = self.root.parent / f"{self.root.name}-{branch_name}"
        return self.run_cmd([
            "git", "worktree", "add",
            str(worktree_path),
            "-b", branch_name,
        ])
