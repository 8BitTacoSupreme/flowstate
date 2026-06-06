"""Tests for context generator — all offline, no bridge needed."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from flowstate.context import (
    generate_claude_md,
    generate_gsd_config,
    generate_project_md,
    generate_research_brief,
    generate_roadmap_md,
    generate_starter_fixture,
    scaffold_mcp_json,
    write_context_files,
)
from flowstate.state import FlowStateModel, InterviewAnswers


class TestGenerateProjectMd:
    def test_basic(self):
        answers = InterviewAnswers(core_problem="Slow deploys", ten_x_vision="One-click")
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

        assert len(created) == 7
        assert (tmp_path / ".planning" / "PROJECT.md").exists()
        assert (tmp_path / ".planning" / "ROADMAP.md").exists()
        assert (tmp_path / ".planning" / "config.json").exists()
        assert (tmp_path / ".claude" / "CLAUDE.md").exists()
        assert (tmp_path / "research" / "brief.md").exists()
        assert (tmp_path / ".planning" / "fixtures" / "starter.json").exists()
        assert (tmp_path / ".mcp.json").exists()

    def test_updates_state_context_files(self, tmp_path: Path):
        state = FlowStateModel()
        write_context_files(state, tmp_path)
        assert len(state.context_files) == 7
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

        assert len(state.install_manifest) == 7
        expected = {
            ".planning/PROJECT.md",
            ".planning/ROADMAP.md",
            ".planning/config.json",
            ".claude/CLAUDE.md",
            "research/brief.md",
            ".planning/fixtures/starter.json",
            ".mcp.json",
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

        assert len(state.install_manifest) == 7

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
        assert by_path[".planning/fixtures/starter.json"].kind == "fixture"
        assert by_path[".mcp.json"].kind == "config"
        # owner is "context" for all (written by context.write_context_files)
        for entry in state.install_manifest:
            assert entry.owner == "context"


class TestGenerateStarterFixture:
    """Tests for generate_starter_fixture() — ECC-modeled fixture generation."""

    FIXTURE_REQUIRED_KEYS: ClassVar[set[str]] = {
        "retrieval_questions",
        "acceptance_gates",
        "forbidden_actions",
        "system_contract",
        "few_shot_exemplars",
    }

    def test_returns_all_required_keys(self):
        answers = InterviewAnswers()
        d = generate_starter_fixture(answers)
        assert set(d.keys()) == self.FIXTURE_REQUIRED_KEYS

    def test_empty_answers_produces_valid_fixture(self):
        """Empty InterviewAnswers still yields a fixture with ≥1 element per list."""
        d = generate_starter_fixture(InterviewAnswers())
        assert len(d["retrieval_questions"]) >= 1
        assert len(d["acceptance_gates"]) >= 1
        assert len(d["forbidden_actions"]) >= 1
        assert isinstance(d["system_contract"], str)
        assert len(d["system_contract"]) > 0
        assert len(d["few_shot_exemplars"]) >= 1

    def test_few_shot_exemplar_shape(self):
        """Each exemplar must have input, expected_output, rationale keys."""
        d = generate_starter_fixture(InterviewAnswers())
        for ex in d["few_shot_exemplars"]:
            assert "input" in ex
            assert "expected_output" in ex
            assert "rationale" in ex

    def test_core_problem_in_system_contract(self):
        """core_problem answer appears in system_contract text."""
        answers = InterviewAnswers(core_problem="Pipeline bottleneck at ingestion layer")
        d = generate_starter_fixture(answers)
        assert "Pipeline bottleneck at ingestion layer" in d["system_contract"]

    def test_milestones_seed_acceptance_gates(self):
        """Milestone answers appear in acceptance_gates."""
        answers = InterviewAnswers(milestones=["Alpha launch", "Beta release", "GA"])
        d = generate_starter_fixture(answers)
        gates_text = " ".join(d["acceptance_gates"])
        assert "Alpha launch" in gates_text or "Alpha" in gates_text

    def test_ten_x_vision_in_retrieval_questions(self):
        """ten_x_vision answer surfaces in retrieval_questions."""
        answers = InterviewAnswers(ten_x_vision="Zero-latency event streaming")
        d = generate_starter_fixture(answers)
        questions_text = " ".join(d["retrieval_questions"])
        assert "Zero-latency event streaming" in questions_text

    def test_project_name_accepted(self):
        """generate_starter_fixture accepts an optional project_name without crashing."""
        answers = InterviewAnswers(core_problem="Slow CI")
        d = generate_starter_fixture(answers, project_name="MyProject")
        assert set(d.keys()) == self.FIXTURE_REQUIRED_KEYS

    def test_coverage_gate_in_acceptance_gates(self):
        """test_coverage value surfaces as a coverage gate in acceptance_gates."""
        answers = InterviewAnswers(test_coverage=90)
        d = generate_starter_fixture(answers)
        gates_text = " ".join(d["acceptance_gates"])
        assert "90" in gates_text


class TestScaffoldMcpJson:
    """Tests for scaffold_mcp_json() — repomix MCP registration."""

    def test_returns_mcp_servers_key(self, tmp_path: Path):
        d = scaffold_mcp_json(tmp_path)
        assert "mcpServers" in d

    def test_repomix_entry_present(self, tmp_path: Path):
        d = scaffold_mcp_json(tmp_path)
        assert "repomix" in d["mcpServers"]

    def test_command_is_npx(self, tmp_path: Path):
        d = scaffold_mcp_json(tmp_path)
        assert d["mcpServers"]["repomix"]["command"] == "npx"

    def test_args_exact_shape(self, tmp_path: Path):
        d = scaffold_mcp_json(tmp_path)
        assert d["mcpServers"]["repomix"]["args"] == ["repomix", "--mcp"]

    def test_exact_dict_shape(self, tmp_path: Path):
        """Full structural assertion matching MEDIUM-3 required shape."""
        d = scaffold_mcp_json(tmp_path)
        assert d == {"mcpServers": {"repomix": {"command": "npx", "args": ["repomix", "--mcp"]}}}


class TestWriteContextFilesFixtureAndMcp:
    """Integration tests: write_context_files creates fixture + .mcp.json."""

    def test_fixture_file_created(self, tmp_path: Path):
        state = FlowStateModel()
        state.interview.core_problem = "Test"
        write_context_files(state, tmp_path)
        fixture_path = tmp_path / ".planning" / "fixtures" / "starter.json"
        assert fixture_path.exists()

    def test_fixture_is_valid_json(self, tmp_path: Path):
        import json

        state = FlowStateModel()
        state.interview.core_problem = "Test"
        write_context_files(state, tmp_path)
        fixture_path = tmp_path / ".planning" / "fixtures" / "starter.json"
        data = json.loads(fixture_path.read_text())
        assert "retrieval_questions" in data
        assert "acceptance_gates" in data
        assert "forbidden_actions" in data
        assert "system_contract" in data
        assert "few_shot_exemplars" in data

    def test_mcp_json_created(self, tmp_path: Path):
        state = FlowStateModel()
        write_context_files(state, tmp_path)
        assert (tmp_path / ".mcp.json").exists()

    def test_mcp_json_content(self, tmp_path: Path):
        import json

        state = FlowStateModel()
        write_context_files(state, tmp_path)
        d = json.loads((tmp_path / ".mcp.json").read_text())
        assert d["mcpServers"]["repomix"]["command"] == "npx"
        assert d["mcpServers"]["repomix"]["args"] == ["repomix", "--mcp"]

    def test_mcp_json_in_context_files(self, tmp_path: Path):
        """'.mcp.json' appears in state.context_files after write_context_files."""
        state = FlowStateModel()
        write_context_files(state, tmp_path)
        assert ".mcp.json" in state.context_files

    def test_fixture_registered_as_fixture_kind(self, tmp_path: Path):
        state = FlowStateModel()
        write_context_files(state, tmp_path)
        by_path = {e.path: e for e in state.install_manifest}
        assert ".planning/fixtures/starter.json" in by_path
        assert by_path[".planning/fixtures/starter.json"].kind == "fixture"
        assert by_path[".planning/fixtures/starter.json"].checksum is not None

    def test_mcp_json_registered_as_config_kind(self, tmp_path: Path):
        state = FlowStateModel()
        write_context_files(state, tmp_path)
        by_path = {e.path: e for e in state.install_manifest}
        assert ".mcp.json" in by_path
        assert by_path[".mcp.json"].kind == "config"
        assert by_path[".mcp.json"].checksum is not None

    def test_creates_7_files(self, tmp_path: Path):
        """write_context_files now produces 7 files (5 original + fixture + .mcp.json)."""
        state = FlowStateModel()
        created = write_context_files(state, tmp_path)
        assert len(created) == 7


class TestGenerateClaudeMdRepomixGuidance:
    """DX-02: generate_claude_md includes repomix-pack guidance."""

    def test_repomix_pack_guidance_present(self):
        state = FlowStateModel()
        result = generate_claude_md(state)
        assert "repomix-pack" in result

    def test_repomix_pack_references_xml_path(self):
        state = FlowStateModel()
        result = generate_claude_md(state)
        assert "repomix-pack.xml" in result
