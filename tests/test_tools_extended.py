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

    def test_run_cmd_env_scrubbed_at_default_observe(self, tmp_path: Path, monkeypatch):
        """run_cmd routes through wrap("tool") — credential-shaped vars dropped, PATH kept."""
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "leaked-secret")
        monkeypatch.setenv("PATH", "/usr/bin:/bin")

        captured: dict = {}
        import subprocess as subprocess_module

        real_run = subprocess_module.run

        def _spy_run(cmd, **kwargs):
            captured["env"] = kwargs.get("env")
            return real_run(cmd, **kwargs)

        monkeypatch.setattr("flowstate.tools.base.subprocess.run", _spy_run)

        adapter = ToolAdapter(root=tmp_path, dry_run=False)
        assert adapter.sandbox == "observe"
        result = adapter.run_cmd(["echo", "hello"])

        assert result.success
        assert captured["env"] is not None
        assert "AWS_SECRET_ACCESS_KEY" not in captured["env"]
        assert captured["env"].get("PATH") == "/usr/bin:/bin"

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

    def test_prior_knowledge_accepted_and_stored(self, tmp_path: Path):
        """ToolAdapter accepts prior_knowledge kwarg and stores it on self."""
        adapter = ToolAdapter(root=tmp_path, prior_knowledge="## Prior Knowledge\n\nfoo")
        assert adapter.prior_knowledge == "## Prior Knowledge\n\nfoo"

    def test_prior_knowledge_default_none_when_omitted(self, tmp_path: Path):
        """ToolAdapter defaults prior_knowledge to None when not provided."""
        adapter = ToolAdapter(root=tmp_path)
        assert adapter.prior_knowledge is None
