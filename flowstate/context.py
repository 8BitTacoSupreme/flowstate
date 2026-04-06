"""Context generator — deterministic file generation from interview answers.

No LLM calls. Pure Python templates. All files consumed by downstream tools
(GSD, Claude Code extensions, research adapters).
"""

from __future__ import annotations

import json
from pathlib import Path
from textwrap import dedent

from flowstate.state import FlowStateModel, InterviewAnswers


def generate_project_md(answers: InterviewAnswers, project_name: str = "") -> str:
    """Generate GSD-format PROJECT.md from interview answers."""
    milestones = (
        "\n".join(f"- {m}" for m in answers.milestones)
        if answers.milestones
        else "- TBD"
    )
    return dedent(f"""\
        # {project_name or "Project"}

        ## Problem
        {answers.core_problem or "Not specified"}

        ## Vision
        {answers.ten_x_vision or "Not specified"}

        ## Architecture
        - Pattern: {answers.architecture_pattern or "not specified"}
        - Test coverage target: {answers.test_coverage}%

        ## Milestones
        {milestones}
    """)


def generate_roadmap_md(answers: InterviewAnswers) -> str:
    """Generate phase-based ROADMAP.md from milestones."""
    if not answers.milestones:
        return dedent("""\
            # Roadmap

            ## Phase 1: Define milestones
            - **Goal**: Establish project milestones
            - **Deliverables**: Milestone list with acceptance criteria
            - **Status**: Pending
        """)

    phases = []
    for i, milestone in enumerate(answers.milestones, 1):
        phases.append(
            dedent(f"""\
            ## Phase {i}: {milestone}
            - **Goal**: {milestone}
            - **Deliverables**: TBD (refine during planning)
            - **Acceptance criteria**: TBD
            - **Status**: Pending""")
        )

    return "# Roadmap\n\n" + "\n\n".join(phases) + "\n"


def generate_gsd_config(preferences: dict | None = None) -> dict:
    """Generate GSD config.json with workflow preferences."""
    defaults = {
        "mode": "balanced",
        "granularity": "standard",
        "auto_commit": True,
        "verification": True,
    }
    if preferences:
        defaults.update(preferences)
    return defaults


def generate_claude_md(state: FlowStateModel) -> str:
    """Generate project-level CLAUDE.md with context for all tools."""
    project_name = state.preferences.project_name or "Project"
    answers = state.interview

    tools_section = ""
    tool_names = list(state.tools.keys())
    if tool_names:
        tools_section = "\n## Active Tools\n" + "\n".join(f"- {t}" for t in tool_names)

    return dedent(f"""\
        # {project_name} — Project Context

        ## Problem
        {answers.core_problem or "Not specified"}

        ## Vision
        {answers.ten_x_vision or "Not specified"}

        ## Architecture
        - Pattern: {answers.architecture_pattern or "not specified"}
        - Test coverage: {answers.test_coverage}%
        {tools_section}

        ## Current Phase
        See `.planning/ROADMAP.md` for phase details.
    """)


def generate_research_brief(answers: InterviewAnswers) -> str:
    """Generate structured research questions from interview answers."""
    topics = [t.strip() for t in answers.research_focus.split(",") if t.strip()]
    if not topics:
        topics = [answers.research_focus or "general"]

    sections = []
    for i, topic in enumerate(topics, 1):
        sections.append(
            dedent(f"""\
            ## Topic {i}: {topic}
            - What are current best practices?
            - What are the top 2-3 approaches and their trade-offs?
            - What is the recommended approach given the architecture ({answers.architecture_pattern or "not specified"})?""")
        )

    header = dedent(f"""\
        # Research Brief

        ## Context
        - Core problem: {answers.core_problem or "Not specified"}
        - Architecture: {answers.architecture_pattern or "not specified"}

    """)

    return header + "\n\n".join(sections) + "\n"


def write_context_files(state: FlowStateModel, root: Path) -> list[Path]:
    """Orchestrate writing all context files. Returns list of created paths."""
    created: list[Path] = []
    answers = state.interview
    project_name = state.preferences.project_name or ""

    # .planning/PROJECT.md
    planning = root / ".planning"
    planning.mkdir(exist_ok=True)

    project_path = planning / "PROJECT.md"
    project_path.write_text(generate_project_md(answers, project_name))
    created.append(project_path)

    # .planning/ROADMAP.md
    roadmap_path = planning / "ROADMAP.md"
    roadmap_path.write_text(generate_roadmap_md(answers))
    created.append(roadmap_path)

    # .planning/config.json
    config_path = planning / "config.json"
    config_path.write_text(json.dumps(generate_gsd_config(), indent=2) + "\n")
    created.append(config_path)

    # .claude/CLAUDE.md (project-level)
    claude_dir = root / ".claude"
    claude_dir.mkdir(exist_ok=True)
    claude_md_path = claude_dir / "CLAUDE.md"
    claude_md_path.write_text(generate_claude_md(state))
    created.append(claude_md_path)

    # research/brief.md
    research_dir = root / "research"
    research_dir.mkdir(exist_ok=True)
    brief_path = research_dir / "brief.md"
    brief_path.write_text(generate_research_brief(answers))
    created.append(brief_path)

    # Track in state
    state.context_files = [str(p.relative_to(root)) for p in created]

    return created
