"""FlowState Interviewer — Rich-powered conversational intake."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.prompt import IntPrompt, Prompt

from flowstate.state import FlowStateModel, InterviewAnswers

console = Console()

SECTIONS = [
    {
        "key": "research",
        "title": "Intelligence (Autoresearch)",
        "color": "cyan",
        "questions": [
            (
                "research_focus",
                "What specific libraries, APIs, or edge cases should we research before starting?",
            ),
        ],
    },
    {
        "key": "strategy",
        "title": "Strategy (Gstack)",
        "color": "yellow",
        "questions": [
            ("core_problem", "What is the core user problem we are solving?"),
            ("ten_x_vision", "What does the 10x version of this look like?"),
        ],
    },
    {
        "key": "management",
        "title": "Management (GSD)",
        "color": "green",
        "questions": [
            (
                "milestones",
                "What are the three most critical milestones for this phase? (comma-separated)",
            ),
        ],
    },
    {
        "key": "discipline",
        "title": "Discipline (Superpowers)",
        "color": "magenta",
        "questions": [
            ("test_coverage", "Required test coverage percentage?"),
            (
                "architecture_pattern",
                "Architectural pattern to follow? (e.g., hexagonal, event-driven, layered)",
            ),
        ],
    },
]


def run_interview(state: FlowStateModel) -> InterviewAnswers:
    answers = state.interview

    console.print()
    console.print(
        Panel(
            "[bold]FlowState Intake Interview[/bold]\n"
            "Answer the following to configure the GrandSlam pipeline.\n"
            "Press Enter to keep defaults shown in brackets.",
            border_style="blue",
        )
    )

    for section in SECTIONS:
        console.print()
        console.rule(f"[bold {section['color']}]{section['title']}[/]")

        for field, question in section["questions"]:
            current = getattr(answers, field, "")
            default_display = current if current else None

            if field == "milestones":
                default_str = ", ".join(current) if current else None
                raw = Prompt.ask(
                    f"  {question}", default=default_str or "", console=console
                )
                raw = raw.replace("\r", "").strip()
                setattr(
                    answers, field, [m.strip() for m in raw.split(",") if m.strip()]
                )
            elif field == "test_coverage":
                val = IntPrompt.ask(
                    f"  {question}", default=current or 80, console=console
                )
                setattr(answers, field, val)
            else:
                val = Prompt.ask(
                    f"  {question}", default=default_display or "", console=console
                )
                setattr(answers, field, val.replace("\r", "").strip())

    # Project name
    console.print()
    console.rule("[bold blue]Project[/]")
    state.preferences.project_name = Prompt.ask(
        "  Project name",
        default=state.preferences.project_name or "flowstate-project",
        console=console,
    )

    console.print()
    console.print("[bold green]Interview complete.[/] Answers captured in state.")
    return answers
