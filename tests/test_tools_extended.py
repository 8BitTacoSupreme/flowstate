"""Extended tests for tool adapters — covers prompt building and base class."""

from __future__ import annotations

from pathlib import Path

from flowstate.state import InterviewAnswers
from flowstate.tools.base import ToolAdapter
from flowstate.tools.research import _build_topic_prompt, _split_topics
from flowstate.tools.strategy import _build_pressure_test_prompt


class TestBuildPrompts:
    def test_research_topic_split(self):
        topics = _split_topics("websockets, gRPC, REST")
        assert len(topics) == 3
        assert topics[0] == "websockets"
        assert topics[1] == "gRPC"
        assert topics[2] == "REST"

    def test_research_single_topic(self):
        topics = _split_topics("websockets")
        assert topics == ["websockets"]

    def test_research_empty_topic(self):
        topics = _split_topics("")
        assert topics == ["general research"]

    def test_research_prompt_basic(self):
        answers = InterviewAnswers(research_focus="websockets")
        prompt = _build_topic_prompt("websockets", answers)
        assert "websockets" in prompt

    def test_research_prompt_with_context(self):
        answers = InterviewAnswers(
            research_focus="websockets",
            core_problem="real-time sync",
            architecture_pattern="event-driven",
        )
        prompt = _build_topic_prompt("websockets", answers)
        assert "real-time sync" in prompt
        assert "event-driven" in prompt

    def test_pressure_test_prompt(self):
        answers = InterviewAnswers(
            core_problem="data pipeline latency",
            ten_x_vision="sub-second processing",
            milestones=["Alpha", "Beta"],
            architecture_pattern="event-driven",
            test_coverage=80,
        )
        prompt = _build_pressure_test_prompt(answers)
        assert "data pipeline latency" in prompt
        assert "sub-second" in prompt
        assert "Alpha" in prompt


class TestToolAdapterBase:
    def test_run_cmd_dry_run(self, tmp_path: Path):
        adapter = ToolAdapter(root=tmp_path, dry_run=True)
        result = adapter.run_cmd(["echo", "hello"])
        assert result.success
        assert "dry-run" in result.output

    def test_run_cmd_success(self, tmp_path: Path):
        adapter = ToolAdapter(root=tmp_path, dry_run=False)
        result = adapter.run_cmd(["echo", "hello"])
        assert result.success
        assert "hello" in result.output

    def test_run_cmd_not_found(self, tmp_path: Path):
        adapter = ToolAdapter(root=tmp_path, dry_run=False)
        result = adapter.run_cmd(["nonexistent_binary_xyz"])
        assert not result.success
        assert "not found" in result.error.lower()

    def test_bridge_auto_created(self, tmp_path: Path):
        adapter = ToolAdapter(root=tmp_path, dry_run=True)
        bridge = adapter.bridge
        assert bridge is not None
        assert bridge.dry_run

    def test_bridge_to_result(self, tmp_path: Path):
        from flowstate.bridge import BridgeResult

        adapter = ToolAdapter(root=tmp_path, dry_run=True)
        br = BridgeResult(success=True, output="test output")
        result = adapter.bridge_to_result(br, artifacts=["a.txt"])
        assert result.success
        assert result.artifacts == ["a.txt"]
