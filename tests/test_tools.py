"""Tests for tool adapters."""

from pathlib import Path

from flowstate.bridge import ClaudeBridge
from flowstate.state import FlowStateModel, InterviewAnswers
from flowstate.tools.gsd_adapter import GSDAdapter
from flowstate.tools.research import ResearchAdapter
from flowstate.tools.strategy import StrategyAdapter


def _mock_bridge() -> ClaudeBridge:
    return ClaudeBridge(dry_run=True)


def test_research_dry_run(tmp_path: Path):
    adapter = ResearchAdapter(root=tmp_path, dry_run=True, bridge=_mock_bridge())
    answers = InterviewAnswers(research_focus="websocket libraries")
    result = adapter.execute(answers)

    assert result.success
    assert (tmp_path / "research" / "report.md").exists()
    content = (tmp_path / "research" / "report.md").read_text()
    assert "websocket libraries" in content


def test_research_multi_topic_dry_run(tmp_path: Path):
    adapter = ResearchAdapter(root=tmp_path, dry_run=True, bridge=_mock_bridge())
    answers = InterviewAnswers(research_focus="websockets, gRPC, REST APIs")
    result = adapter.execute(answers)

    assert result.success
    content = (tmp_path / "research" / "report.md").read_text()
    assert "websockets" in content
    assert "gRPC" in content
    assert "REST APIs" in content


def test_strategy_dry_run(tmp_path: Path):
    adapter = StrategyAdapter(root=tmp_path, dry_run=True, bridge=_mock_bridge())
    answers = InterviewAnswers(core_problem="Slow deploys", ten_x_vision="One-click shipping")

    result = adapter.pressure_test(answers)
    assert result.success
    assert (tmp_path / "research" / "strategy.md").exists()


def test_gsd_dry_run(tmp_path: Path):
    adapter = GSDAdapter(root=tmp_path, dry_run=True, bridge=_mock_bridge())
    state = FlowStateModel()
    state.interview.milestones = ["Alpha", "Beta", "GA"]
    result = adapter.new_project(state)

    assert result.success
    content = (tmp_path / ".planning" / "ROADMAP.md").read_text()
    assert "Alpha" in content
    assert "Beta" in content


def test_gsd_live_writes_context_files(tmp_path: Path):
    adapter = GSDAdapter(root=tmp_path, dry_run=False, bridge=_mock_bridge())
    state = FlowStateModel()
    state.interview.milestones = ["Alpha", "Beta"]
    state.interview.core_problem = "Test problem"
    state.preferences.project_name = "test-proj"
    result = adapter.new_project(state)

    assert result.success
    assert (tmp_path / ".planning" / "PROJECT.md").exists()
    assert (tmp_path / ".planning" / "ROADMAP.md").exists()
    assert (tmp_path / ".claude" / "CLAUDE.md").exists()
    assert (tmp_path / "research" / "brief.md").exists()


def test_research_passes_model_to_bridge(tmp_path: Path, monkeypatch):
    """Research adapter passes model='sonnet' to bridge.run()."""
    from unittest.mock import MagicMock

    from flowstate.bridge import BridgeResult

    bridge = MagicMock()
    bridge.run.return_value = BridgeResult(success=True, output="# Research", exit_code=0)

    adapter = ResearchAdapter(root=tmp_path, dry_run=False, bridge=bridge)
    answers = InterviewAnswers(research_focus="websockets")
    adapter.execute(answers)

    call_kwargs = bridge.run.call_args[1]
    assert call_kwargs["model"] == "sonnet"


def test_lazy_bridge_threads_sandbox_tier(tmp_path: Path):
    """SBX-03: the lazily-built .bridge inherits the adapter's confinement tier,
    so a caller on this path is not silently downgraded to observe."""
    adapter = ResearchAdapter(root=tmp_path, dry_run=False, sandbox="confine")
    # No explicit bridge injected -> the .bridge property builds one lazily.
    assert adapter.bridge.config.sandbox == "confine"


def test_strategy_passes_model_to_bridge(tmp_path: Path):
    """Strategy adapter passes model='sonnet' to bridge.run()."""
    from unittest.mock import MagicMock

    from flowstate.bridge import BridgeResult

    bridge = MagicMock()
    bridge.run.return_value = BridgeResult(success=True, output="# Strategy", exit_code=0)

    adapter = StrategyAdapter(root=tmp_path, dry_run=False, bridge=bridge)
    answers = InterviewAnswers(core_problem="Slow deploys", ten_x_vision="Fast")
    adapter.pressure_test(answers)

    call_kwargs = bridge.run.call_args[1]
    assert call_kwargs["model"] == "sonnet"


# -- Unified prior_knowledge injection (quick-m9v) --


def test_research_prepends_injected_prior_knowledge(tmp_path: Path):
    """ResearchAdapter prepends self.prior_knowledge to every per-topic prompt."""
    from unittest.mock import MagicMock

    from flowstate.bridge import BridgeResult

    bridge = MagicMock()
    bridge.run.return_value = BridgeResult(success=True, output="# Findings", exit_code=0)

    prior = "## Prior Knowledge\n\nINJECTED_MARKER\n"
    adapter = ResearchAdapter(
        root=tmp_path,
        dry_run=False,
        bridge=bridge,
        prior_knowledge=prior,
    )
    answers = InterviewAnswers(research_focus="websockets, gRPC, REST")
    adapter.execute(answers)

    # Every per-topic prompt must start with the injected block followed by '\n\n---\n\n'.
    assert bridge.run.call_count == 3
    for call in bridge.run.call_args_list:
        prompt = call.args[0]
        assert prompt.startswith(prior + "\n\n---\n\n"), (
            f"prompt did not start with injected prior_knowledge block: {prompt[:200]!r}"
        )
        assert "INJECTED_MARKER" in prompt


def test_research_no_prior_knowledge_no_prefix(tmp_path: Path):
    """ResearchAdapter does not prepend any '## Prior Knowledge' block when none provided."""
    from unittest.mock import MagicMock

    from flowstate.bridge import BridgeResult

    bridge = MagicMock()
    bridge.run.return_value = BridgeResult(success=True, output="# Findings", exit_code=0)

    # No prior_knowledge, no memory store
    adapter = ResearchAdapter(root=tmp_path, dry_run=False, bridge=bridge)
    answers = InterviewAnswers(research_focus="websockets, gRPC")
    adapter.execute(answers)

    for call in bridge.run.call_args_list:
        prompt = call.args[0]
        assert "## Prior Knowledge" not in prompt, (
            f"unexpected '## Prior Knowledge' substring in prompt: {prompt[:200]!r}"
        )


def test_strategy_prepends_injected_prior_knowledge(tmp_path: Path):
    """StrategyAdapter prepends self.prior_knowledge to the pressure-test prompt."""
    from unittest.mock import MagicMock

    from flowstate.bridge import BridgeResult

    bridge = MagicMock()
    bridge.run.return_value = BridgeResult(success=True, output="# Strategy", exit_code=0)

    prior = "## Prior Knowledge\n\nINJECTED_STRATEGY_MARKER\n"
    adapter = StrategyAdapter(
        root=tmp_path,
        dry_run=False,
        bridge=bridge,
        prior_knowledge=prior,
    )
    answers = InterviewAnswers(core_problem="Slow deploys", ten_x_vision="Fast")
    adapter.pressure_test(answers)

    assert bridge.run.call_count == 1
    prompt = bridge.run.call_args.args[0]
    assert prompt.startswith(prior + "\n\n---\n\n"), (
        f"strategy prompt did not start with injected prior_knowledge: {prompt[:200]!r}"
    )
    assert "INJECTED_STRATEGY_MARKER" in prompt


def test_research_does_not_call_get_memory_context_when_prior_knowledge_set(
    tmp_path: Path, monkeypatch
):
    """When prior_knowledge is supplied, ResearchAdapter must NOT call memory.get_context()."""
    from unittest.mock import MagicMock

    from flowstate.bridge import BridgeResult
    from flowstate.memory import MemoryStore

    bridge = MagicMock()
    bridge.run.return_value = BridgeResult(success=True, output="# Findings", exit_code=0)

    memory = MemoryStore(root=tmp_path)
    call_count = {"n": 0}

    def spy(self, query, *, max_tokens: int = 2000):  # type: ignore[no-untyped-def]
        call_count["n"] += 1
        return ""

    monkeypatch.setattr(MemoryStore, "get_context", spy)

    adapter = ResearchAdapter(
        root=tmp_path,
        dry_run=False,
        bridge=bridge,
        memory=memory,
        prior_knowledge="## Prior Knowledge\n\nfoo",
    )
    answers = InterviewAnswers(research_focus="websockets, gRPC, REST")
    adapter.execute(answers)

    memory.close()
    assert call_count["n"] == 0, (
        f"memory.get_context should not be called when prior_knowledge is set "
        f"(called {call_count['n']} times)"
    )


# -- Bounded retry + raised max_turns (quick-260613-m60) --


def test_research_retries_then_succeeds(tmp_path: Path):
    """First attempt fails; second attempt succeeds — report has good output, not placeholder."""
    from unittest.mock import MagicMock

    from flowstate.bridge import BridgeResult

    bridge = MagicMock()
    bridge.run.side_effect = [
        BridgeResult(success=False, output="", exit_code=1, error="Reached max turns"),
        BridgeResult(success=True, output="GOOD SECTION", exit_code=0),
    ]

    adapter = ResearchAdapter(root=tmp_path, dry_run=False, bridge=bridge)
    answers = InterviewAnswers(research_focus="websockets")
    adapter.execute(answers)

    assert bridge.run.call_count == 2
    report = (tmp_path / "research" / "report.md").read_text()
    assert "GOOD SECTION" in report
    assert "*Research failed:" not in report


def test_research_all_attempts_fail(tmp_path: Path):
    """All attempts fail — placeholder appears in report; bridge called _RESEARCH_MAX_ATTEMPTS times;
    result reports success=False (HON-03: the notice never coexists with success=True)."""
    from unittest.mock import MagicMock

    from flowstate.bridge import BridgeResult
    from flowstate.tools.research import _RESEARCH_MAX_ATTEMPTS

    bridge = MagicMock()
    bridge.run.return_value = BridgeResult(success=False, output="", exit_code=1, error="boom")

    adapter = ResearchAdapter(root=tmp_path, dry_run=False, bridge=bridge)
    answers = InterviewAnswers(research_focus="websockets")
    result = adapter.execute(answers)

    assert bridge.run.call_count == _RESEARCH_MAX_ATTEMPTS
    report = (tmp_path / "research" / "report.md").read_text()
    assert "*Research failed:" in report
    assert "boom" in report
    assert result.success is False
    assert result.error is not None


def test_research_partial_success_stays_true(tmp_path: Path):
    """One topic fails all attempts, the other succeeds — result stays success=True and
    the report contains both the successful output and the failure notice (HON-03)."""
    from unittest.mock import MagicMock

    from flowstate.bridge import BridgeResult

    bridge = MagicMock()
    bridge.run.side_effect = [
        BridgeResult(success=False, output="", exit_code=1, error="boom"),
        BridgeResult(success=False, output="", exit_code=1, error="boom"),
        BridgeResult(success=False, output="", exit_code=1, error="boom"),
        BridgeResult(success=True, output="GOOD SECTION", exit_code=0),
    ]

    adapter = ResearchAdapter(root=tmp_path, dry_run=False, bridge=bridge)
    answers = InterviewAnswers(research_focus="websockets, gRPC")
    result = adapter.execute(answers)

    assert result.success is True
    report = (tmp_path / "research" / "report.md").read_text()
    assert "GOOD SECTION" in report
    assert "*Research failed:" in report


def test_research_first_try_success_no_retry(tmp_path: Path):
    """First attempt succeeds — bridge called exactly once; no placeholder in report."""
    from unittest.mock import MagicMock

    from flowstate.bridge import BridgeResult

    bridge = MagicMock()
    bridge.run.return_value = BridgeResult(success=True, output="ONE SHOT", exit_code=0)

    adapter = ResearchAdapter(root=tmp_path, dry_run=False, bridge=bridge)
    answers = InterviewAnswers(research_focus="websockets")
    adapter.execute(answers)

    assert bridge.run.call_count == 1
    report = (tmp_path / "research" / "report.md").read_text()
    assert "ONE SHOT" in report


def test_research_empty_output_is_retried(tmp_path: Path):
    """Blank/whitespace output on first attempt is treated as failure and retried."""
    from unittest.mock import MagicMock

    from flowstate.bridge import BridgeResult

    bridge = MagicMock()
    bridge.run.side_effect = [
        BridgeResult(success=True, output="   ", exit_code=0),
        BridgeResult(success=True, output="REAL", exit_code=0),
    ]

    adapter = ResearchAdapter(root=tmp_path, dry_run=False, bridge=bridge)
    answers = InterviewAnswers(research_focus="websockets")
    adapter.execute(answers)

    assert bridge.run.call_count == 2
    report = (tmp_path / "research" / "report.md").read_text()
    assert "REAL" in report


def test_research_uses_max_turns_six(tmp_path: Path):
    """Each bridge.run() call uses max_turns == _RESEARCH_MAX_TURNS == 6."""
    from unittest.mock import MagicMock

    from flowstate.bridge import BridgeResult
    from flowstate.tools.research import _RESEARCH_MAX_TURNS

    bridge = MagicMock()
    bridge.run.return_value = BridgeResult(success=True, output="x", exit_code=0)

    adapter = ResearchAdapter(root=tmp_path, dry_run=False, bridge=bridge)
    answers = InterviewAnswers(research_focus="websockets")
    adapter.execute(answers)

    assert _RESEARCH_MAX_TURNS == 6
    call_kwargs = bridge.run.call_args[1]
    assert call_kwargs["max_turns"] == _RESEARCH_MAX_TURNS


def test_research_dry_run_zero_bridge_calls(tmp_path: Path):
    """dry_run=True makes zero bridge.run() calls and still writes the mock report."""
    from unittest.mock import MagicMock

    bridge = MagicMock()
    adapter = ResearchAdapter(root=tmp_path, dry_run=True, bridge=bridge)
    answers = InterviewAnswers(research_focus="websockets")
    adapter.execute(answers)

    assert bridge.run.call_count == 0
    assert (tmp_path / "research" / "report.md").exists()


# -- Adapters surface failure honestly (Phase 12: HON-04) --


def test_strategy_empty_output_fails(tmp_path: Path):
    """Bridge succeeds but returns whitespace-only output — strategy reports success=False
    and does not write strategy.md."""
    from unittest.mock import MagicMock

    from flowstate.bridge import BridgeResult

    bridge = MagicMock()
    bridge.run.return_value = BridgeResult(success=True, output="   ", exit_code=0)

    adapter = StrategyAdapter(root=tmp_path, dry_run=False, bridge=bridge)
    answers = InterviewAnswers(core_problem="Slow deploys", ten_x_vision="Fast")
    result = adapter.pressure_test(answers)

    assert result.success is False
    assert not (tmp_path / "research" / "strategy.md").exists()


def test_strategy_bridge_failure_fails(tmp_path: Path):
    """Bridge call itself fails — strategy reports success=False and does not write strategy.md."""
    from unittest.mock import MagicMock

    from flowstate.bridge import BridgeResult

    bridge = MagicMock()
    bridge.run.return_value = BridgeResult(success=False, output="", exit_code=1, error="boom")

    adapter = StrategyAdapter(root=tmp_path, dry_run=False, bridge=bridge)
    answers = InterviewAnswers(core_problem="Slow deploys", ten_x_vision="Fast")
    result = adapter.pressure_test(answers)

    assert result.success is False
    assert not (tmp_path / "research" / "strategy.md").exists()
