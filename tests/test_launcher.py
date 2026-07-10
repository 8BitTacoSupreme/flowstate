"""Tests for launcher module — tool detection and command generation."""

from pathlib import Path

from flowstate import launcher
from flowstate.launcher import detect_tools, launch_command, print_next_steps
from flowstate.state import FlowStateModel


class TestDetectTools:
    def test_builtin_tools_available(self, tmp_path: Path):
        tools = detect_tools(tmp_path)
        # strategy and discipline are built-in, always available
        assert tools["strategy"]
        assert tools["discipline"]

    def test_gsd_always_available(self, tmp_path: Path):
        # GSD is vendored + installed unconditionally (GSD-03); no marker gate.
        # A fresh project with no .planning dir still reports gsd available.
        tools = detect_tools(tmp_path)
        assert tools["gsd"]

    def test_gsd_available_with_planning(self, tmp_path: Path):
        (tmp_path / ".planning").mkdir()
        tools = detect_tools(tmp_path)
        assert tools["gsd"]


class TestLaunchCommand:
    def test_gsd_with_phase(self, tmp_path: Path):
        cmd = launch_command("gsd", 1, tmp_path)
        assert "/gsd:plan-phase 1" in cmd
        assert str(tmp_path) in cmd

    def test_gsd_without_phase(self, tmp_path: Path):
        cmd = launch_command("gsd", None, tmp_path)
        assert "/gsd:progress" in cmd

    def test_research_command(self, tmp_path: Path):
        cmd = launch_command("research", None, tmp_path)
        assert "flowstate init" in cmd

    def test_strategy_command(self, tmp_path: Path):
        # strategy is now a skill-gated handoff (VEND-04); with no gstack skills
        # installed it directs the user to install them (see test_launcher_skills).
        cmd = launch_command("strategy", None, tmp_path)
        assert "install-skills" in cmd

    def test_gsd_fresh_project_no_planning(self, tmp_path: Path):
        # No .planning dir — the handoff must still work, with no "not detected" text.
        cmd = launch_command("gsd", 1, tmp_path)
        assert "/gsd:plan-phase 1" in cmd
        assert "not detected" not in cmd
        assert "new-project" not in cmd

    def test_unknown_tool(self, tmp_path: Path):
        cmd = launch_command("nonexistent", None, tmp_path)
        assert "Unknown tool" in cmd


class TestPrintNextSteps:
    def test_no_gsd_not_detected_branch(self, tmp_path: Path):
        # A project without .planning must never surface the old
        # "GSD not detected / run /gsd:new-project" suggestion (GSD-03).
        state = FlowStateModel()
        with launcher.console.capture() as cap:
            print_next_steps(state, tmp_path)
        out = cap.get()
        assert "not detected" not in out
        assert "new-project" not in out
        assert "flowstate launch gsd 1" in out
