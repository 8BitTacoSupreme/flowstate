"""Tests for context generator — all offline, no bridge needed."""

from pathlib import Path

from flowstate.context import (
    generate_claude_md,
    generate_gsd_config,
    generate_project_md,
    generate_research_brief,
    generate_roadmap_md,
    write_context_files,
)
from flowstate.state import FlowStateModel, InterviewAnswers


class TestGenerateProjectMd:
    def test_basic(self):
        answers = InterviewAnswers(
            core_problem="Slow deploys", ten_x_vision="One-click"
        )
        result = generate_project_md(answers, "TestProj")
        assert "# TestProj" in result
        assert "Slow deploys" in result
        assert "One-click" in result

    def test_with_milestones(self):
        answers = InterviewAnswers(milestones=["Alpha", "Beta", "GA"])
        result = generate_project_md(answers)
        assert "- Alpha" in result
        assert "- Beta" in result
        assert "- GA" in result

    def test_empty_defaults(self):
        answers = InterviewAnswers()
        result = generate_project_md(answers)
        assert "Not specified" in result

    def test_architecture(self):
        answers = InterviewAnswers(architecture_pattern="hexagonal", test_coverage=90)
        result = generate_project_md(answers)
        assert "hexagonal" in result
        assert "90%" in result


class TestGenerateRoadmapMd:
    def test_with_milestones(self):
        answers = InterviewAnswers(milestones=["Alpha", "Beta", "GA"])
        result = generate_roadmap_md(answers)
        assert "Phase 1: Alpha" in result
        assert "Phase 2: Beta" in result
        assert "Phase 3: GA" in result

    def test_empty_milestones(self):
        answers = InterviewAnswers()
        result = generate_roadmap_md(answers)
        assert "Phase 1: Define milestones" in result


class TestGenerateGsdConfig:
    def test_defaults(self):
        config = generate_gsd_config()
        assert config["mode"] == "balanced"
        assert config["verification"] is True

    def test_custom_preferences(self):
        config = generate_gsd_config({"mode": "fast", "custom_key": "value"})
        assert config["mode"] == "fast"
        assert config["custom_key"] == "value"


class TestGenerateClaudeMd:
    def test_basic(self):
        state = FlowStateModel()
        state.preferences.project_name = "MyProject"
        state.interview.core_problem = "Slow builds"
        result = generate_claude_md(state)
        assert "MyProject" in result
        assert "Slow builds" in result

    def test_includes_tools(self):
        state = FlowStateModel()
        result = generate_claude_md(state)
        assert "research" in result
        assert "strategy" in result
        assert "gsd" in result
        assert "discipline" in result


class TestGenerateResearchBrief:
    def test_single_topic(self):
        answers = InterviewAnswers(research_focus="websockets")
        result = generate_research_brief(answers)
        assert "Topic 1: websockets" in result

    def test_multi_topic(self):
        answers = InterviewAnswers(research_focus="websockets, gRPC, REST")
        result = generate_research_brief(answers)
        assert "Topic 1: websockets" in result
        assert "Topic 2: gRPC" in result
        assert "Topic 3: REST" in result

    def test_includes_context(self):
        answers = InterviewAnswers(
            research_focus="websockets",
            core_problem="real-time sync",
            architecture_pattern="event-driven",
        )
        result = generate_research_brief(answers)
        assert "real-time sync" in result
        assert "event-driven" in result


class TestWriteContextFiles:
    def test_creates_all_files(self, tmp_path: Path):
        state = FlowStateModel()
        state.preferences.project_name = "test-proj"
        state.interview.core_problem = "Test problem"
        state.interview.milestones = ["Phase 1", "Phase 2"]
        state.interview.research_focus = "testing"

        created = write_context_files(state, tmp_path)

        assert len(created) == 5
        assert (tmp_path / ".planning" / "PROJECT.md").exists()
        assert (tmp_path / ".planning" / "ROADMAP.md").exists()
        assert (tmp_path / ".planning" / "config.json").exists()
        assert (tmp_path / ".claude" / "CLAUDE.md").exists()
        assert (tmp_path / "research" / "brief.md").exists()

    def test_updates_state_context_files(self, tmp_path: Path):
        state = FlowStateModel()
        write_context_files(state, tmp_path)
        assert len(state.context_files) == 5
        assert ".planning/PROJECT.md" in state.context_files

    def test_idempotent(self, tmp_path: Path):
        state = FlowStateModel()
        state.interview.core_problem = "Test"

        write_context_files(state, tmp_path)
        first_content = (tmp_path / ".planning" / "PROJECT.md").read_text()

        write_context_files(state, tmp_path)
        second_content = (tmp_path / ".planning" / "PROJECT.md").read_text()

        assert first_content == second_content
