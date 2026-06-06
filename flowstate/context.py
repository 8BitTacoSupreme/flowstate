"""Context generator — deterministic file generation from interview answers.

No LLM calls. Pure Python templates. All files consumed by downstream tools
(GSD, Claude Code extensions, research adapters).
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from textwrap import dedent

from flowstate.state import FlowStateModel, InstallEntry, InterviewAnswers


def _sha256_of(path: Path) -> str:
    """Return the hex sha256 digest of a file's contents."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _register(
    state: FlowStateModel,
    root: Path,
    path: Path,
    *,
    owner: str,
    kind: str,
) -> None:
    """Add or replace an InstallEntry for the given file on state.install_manifest.

    Idempotent: removes any existing entry for the same relative path before appending.
    Checksums are computed for all kinds except "memory" (memory.db mutates).
    """
    rel = str(path.relative_to(root))
    checksum = _sha256_of(path) if kind != "memory" else None
    state.install_manifest = [e for e in state.install_manifest if e.path != rel]
    state.install_manifest.append(
        InstallEntry(
            path=rel,
            owner=owner,
            kind=kind,  # type: ignore[arg-type]
            created_at=datetime.now(UTC),
            checksum=checksum,
        )
    )


def generate_project_md(answers: InterviewAnswers, project_name: str = "") -> str:
    """Generate GSD-format PROJECT.md from interview answers."""
    milestones = "\n".join(f"- {m}" for m in answers.milestones) if answers.milestones else "- TBD"
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

        ## Repomix Pack
        When analyzing this codebase, consult `.planning/codebase/repomix-pack.xml`
        instead of crawling source files each wave. The pack is updated by `flowstate pack`.
        Use the repomix MCP server (`mcp__repomix`) for targeted retrieval from the pack.
    """)


def generate_starter_fixture(answers: InterviewAnswers, project_name: str = "") -> dict:
    """Generate a starter ECC-modeled fixture dict from interview answers.

    Returns a dict with all five required keys:
      retrieval_questions, acceptance_gates, forbidden_actions,
      system_contract, few_shot_exemplars (≥1 exemplar).

    Content is derived from interview answers — no LLM, no I/O.
    """
    name = project_name or "this project"

    # system_contract — derived from core_problem
    if answers.core_problem:
        system_contract = (
            f"The agent operates on {name}. "
            f"Core problem: {answers.core_problem}. "
            f"The agent must address this problem faithfully without inventing requirements "
            f"or scope not established in PROJECT.md."
        )
    else:
        system_contract = (
            f"The agent operates on {name}. "
            f"It must address the project's stated problem faithfully, "
            f"without inventing requirements or scope not established in PROJECT.md."
        )

    # retrieval_questions — seeded from ten_x_vision + architecture_pattern
    retrieval_questions: list[str] = []
    if answers.ten_x_vision:
        retrieval_questions.append(
            f"How does this change advance the vision: '{answers.ten_x_vision}'?"
        )
    if answers.architecture_pattern:
        retrieval_questions.append(
            f"Does this approach align with the '{answers.architecture_pattern}' architecture pattern?"
        )
    if not retrieval_questions:
        retrieval_questions.append(
            "Does this change advance the project's stated vision and goals?"
        )

    # acceptance_gates — seeded from milestones + coverage target
    acceptance_gates: list[str] = []
    for milestone in answers.milestones:
        acceptance_gates.append(f"Milestone satisfied: {milestone}")
    acceptance_gates.append(f"Test coverage meets or exceeds {answers.test_coverage}% as required.")
    if len(acceptance_gates) == 1:
        # Only the coverage gate — add a generic functional gate
        acceptance_gates.insert(0, "All described functionality works as specified in PROJECT.md.")

    # forbidden_actions — sensible defaults
    forbidden_actions = [
        "Do not invent requirements not established in PROJECT.md.",
        "Do not modify files outside the stated task scope.",
        "Do not skip or disable tests to reach coverage targets.",
        "Do not introduce new runtime dependencies without explicit approval.",
    ]

    # few_shot_exemplars — at least one exemplar
    few_shot_exemplars = [
        {
            "input": f"Implement the first milestone for {name}.",
            "expected_output": (
                "A focused implementation that satisfies the acceptance gates, "
                "passes all tests, and does not introduce scope beyond what was described."
            ),
            "rationale": (
                "The agent should address the stated problem directly, "
                "verify against acceptance gates, and avoid scope creep."
            ),
        }
    ]

    return {
        "retrieval_questions": retrieval_questions,
        "acceptance_gates": acceptance_gates,
        "forbidden_actions": forbidden_actions,
        "system_contract": system_contract,
        "few_shot_exemplars": few_shot_exemplars,
    }


def scaffold_mcp_json(root: Path) -> dict:
    """Return .mcp.json content registering the repomix MCP server.

    Returns the exact dict shape required by MEDIUM-3:
      {"mcpServers": {"repomix": {"command": "npx", "args": ["repomix", "--mcp"]}}}

    Pure function — no file I/O.
    """
    return {"mcpServers": {"repomix": {"command": "npx", "args": ["repomix", "--mcp"]}}}


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
    _register(state, root, project_path, owner="context", kind="context")
    created.append(project_path)

    # .planning/ROADMAP.md
    roadmap_path = planning / "ROADMAP.md"
    roadmap_path.write_text(generate_roadmap_md(answers))
    _register(state, root, roadmap_path, owner="context", kind="context")
    created.append(roadmap_path)

    # .planning/config.json
    config_path = planning / "config.json"
    config_path.write_text(json.dumps(generate_gsd_config(), indent=2) + "\n")
    _register(state, root, config_path, owner="context", kind="config")
    created.append(config_path)

    # .claude/CLAUDE.md (project-level)
    claude_dir = root / ".claude"
    claude_dir.mkdir(exist_ok=True)
    claude_md_path = claude_dir / "CLAUDE.md"
    claude_md_path.write_text(generate_claude_md(state))
    _register(state, root, claude_md_path, owner="context", kind="context")
    created.append(claude_md_path)

    # research/brief.md
    research_dir = root / "research"
    research_dir.mkdir(exist_ok=True)
    brief_path = research_dir / "brief.md"
    brief_path.write_text(generate_research_brief(answers))
    _register(state, root, brief_path, owner="context", kind="research")
    created.append(brief_path)

    # .planning/fixtures/starter.json (FIX-02)
    fixtures_dir = planning / "fixtures"
    fixtures_dir.mkdir(exist_ok=True)
    fixture_path = fixtures_dir / "starter.json"
    fixture_path.write_text(
        json.dumps(generate_starter_fixture(answers, project_name), indent=2) + "\n"
    )
    _register(state, root, fixture_path, owner="context", kind="fixture")
    created.append(fixture_path)

    # .mcp.json — repomix MCP server registration (PACK-03)
    mcp_path = root / ".mcp.json"
    mcp_path.write_text(json.dumps(scaffold_mcp_json(root), indent=2) + "\n")
    _register(state, root, mcp_path, owner="context", kind="config")
    created.append(mcp_path)

    # Track in state — include .mcp.json in context_files (MEDIUM-5)
    state.context_files = [str(p.relative_to(root)) for p in created]

    return created
