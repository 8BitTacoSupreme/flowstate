"""Tests for launcher module — tool detection and command generation."""

from pathlib import Path

from flowstate.launcher import detect_tools, launch_command


class TestDetectTools:
    def test_no_tools(self, tmp_path: Path):
        tools = detect_tools(tmp_path)
        assert not tools["gsd"]
        # strategy and discipline are built-in, always available
        assert tools["strategy"]
        assert tools["discipline"]

    def test_gsd_detected(self, tmp_path: Path):
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
        cmd = launch_command("strategy", None, tmp_path)
        assert "flowstate init" in cmd

    def test_unknown_tool(self, tmp_path: Path):
        cmd = launch_command("nonexistent", None, tmp_path)
        assert "Unknown tool" in cmd
