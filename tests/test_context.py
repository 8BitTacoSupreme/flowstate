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


class TestWriteContextFilesManifest:
    def test_write_context_files_populates_manifest(self, tmp_path: Path):
        """write_context_files appends 5 InstallEntry rows to state.install_manifest."""
        state = FlowStateModel()
        state.preferences.project_name = "test-proj"
        state.interview.core_problem = "Slow"
        state.interview.research_focus = "x"

        write_context_files(state, tmp_path)

        assert len(state.install_manifest) == 5
        expected = {
            ".planning/PROJECT.md",
            ".planning/ROADMAP.md",
            ".planning/config.json",
            ".claude/CLAUDE.md",
            "research/brief.md",
        }
        actual = {e.path for e in state.install_manifest}
        assert actual == expected
        # All entries have sha256 checksums (64 hex chars)
        for entry in state.install_manifest:
            assert entry.checksum is not None
            assert len(entry.checksum) == 64
            assert all(c in "0123456789abcdef" for c in entry.checksum)

    def test_write_context_files_is_idempotent_for_manifest(self, tmp_path: Path):
        """Re-running write_context_files does not duplicate entries."""
        state = FlowStateModel()
        state.interview.core_problem = "x"
        state.interview.research_focus = "y"

        write_context_files(state, tmp_path)
        write_context_files(state, tmp_path)

        assert len(state.install_manifest) == 5

    def test_write_context_files_kind_mapping(self, tmp_path: Path):
        """config.json -> config; brief.md -> research; PROJECT.md -> context."""
        state = FlowStateModel()
        state.interview.core_problem = "x"
        state.interview.research_focus = "y"

        write_context_files(state, tmp_path)

        by_path = {e.path: e for e in state.install_manifest}
        assert by_path[".planning/config.json"].kind == "config"
        assert by_path["research/brief.md"].kind == "research"
        assert by_path[".planning/PROJECT.md"].kind == "context"
        assert by_path[".planning/ROADMAP.md"].kind == "context"
        assert by_path[".claude/CLAUDE.md"].kind == "context"
        # owner is "context" for all (written by context.write_context_files)
        for entry in state.install_manifest:
            assert entry.owner == "context"
