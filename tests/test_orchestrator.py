"""Tests for FlowState orchestrator — dry-run pipeline."""

from pathlib import Path

from flowstate.orchestrator import run_pipeline
from flowstate.state import FlowStateModel, ToolStatus


def test_dry_run_pipeline(tmp_path: Path):
    state = FlowStateModel()
    state.preferences.dry_run = True
    state.preferences.project_name = "test-proj"
    state.interview.research_focus = "REST API design"
    state.interview.core_problem = "Developer onboarding is slow"
    state.interview.ten_x_vision = "Zero-config project setup"
    state.interview.milestones = ["Intake", "Pipeline", "Polish"]
    state.interview.test_coverage = 85
    state.interview.architecture_pattern = "hexagonal"

    result = run_pipeline(state, tmp_path)

    # All tools should complete in dry-run
    for name, ts in result.tools.items():
        assert ts.status == ToolStatus.COMPLETED, f"{name} not completed: {ts.status}"

    # Artifacts should be created
    assert (tmp_path / "research" / "report.md").exists()
    assert (tmp_path / "research" / "strategy.md").exists()
    assert (tmp_path / ".planning" / "ROADMAP.md").exists()


def test_dry_run_creates_state_file(tmp_path: Path):
    state = FlowStateModel()
    state.preferences.dry_run = True
    run_pipeline(state, tmp_path)

    assert (tmp_path / "flowstate.json").exists()


def test_dry_run_creates_context_files(tmp_path: Path):
    state = FlowStateModel()
    state.preferences.dry_run = True
    state.interview.research_focus = "testing"
    state.interview.core_problem = "slow tests"
    state.preferences.project_name = "ctx-test"

    run_pipeline(state, tmp_path)

    # Context generation should create these files
    assert (tmp_path / ".planning" / "PROJECT.md").exists()
    assert (tmp_path / ".claude" / "CLAUDE.md").exists()
    assert (tmp_path / "research" / "brief.md").exists()


def test_run_pipeline_registers_tool_artifacts(tmp_path: Path):
    """Tool adapters that write artifacts get registered on install_manifest."""
    state = FlowStateModel()
    state.preferences.dry_run = True
    state.interview.research_focus = "testing"
    state.interview.core_problem = "Test problem"

    run_pipeline(state, tmp_path)

    # The research adapter writes research/report.md in dry-run mode
    research_entries = [
        e
        for e in state.install_manifest
        if e.owner == "research" and e.kind in {"research", "artifact"}
    ]
    assert len(research_entries) >= 1, (
        f"expected at least one research-owned manifest entry, got: "
        f"{[(e.path, e.owner, e.kind) for e in state.install_manifest]}"
    )
    # Strategy adapter also writes research/strategy.md
    strategy_entries = [e for e in state.install_manifest if e.owner == "strategy"]
    assert len(strategy_entries) >= 1


def test_pipeline_builds_prior_knowledge_once_and_threads_it(tmp_path: Path, monkeypatch):
    """End-to-end: prior_knowledge built exactly once and threaded to every adapter.

    Proves the unified-injection contract (quick-m9v):
    - MemoryStore.get_context() called at most once per pipeline run
    - Research + Strategy + GSD adapters all receive the same prior_knowledge value
    """
    from flowstate.memory import MemoryStore
    from flowstate.tools.gsd_adapter import GSDAdapter
    from flowstate.tools.research import ResearchAdapter
    from flowstate.tools.strategy import StrategyAdapter

    # Spy on MemoryStore.get_context — count calls, capture last query
    get_context_calls = {"n": 0, "queries": []}
    original_get_context = MemoryStore.get_context

    def spy_get_context(self, query, *, max_tokens: int = 2000):
        get_context_calls["n"] += 1
        get_context_calls["queries"].append(query)
        return original_get_context(self, query, max_tokens=max_tokens)

    monkeypatch.setattr(MemoryStore, "get_context", spy_get_context)

    # Record kwargs passed to each adapter's __init__
    init_records: dict[str, dict] = {}

    def make_recording_init(cls, name):
        original_init = cls.__init__

        def recording_init(self, *args, **kwargs):
            init_records[name] = dict(kwargs)
            original_init(self, *args, **kwargs)

        return recording_init

    monkeypatch.setattr(
        ResearchAdapter, "__init__", make_recording_init(ResearchAdapter, "research")
    )
    monkeypatch.setattr(
        StrategyAdapter, "__init__", make_recording_init(StrategyAdapter, "strategy")
    )
    monkeypatch.setattr(GSDAdapter, "__init__", make_recording_init(GSDAdapter, "gsd"))

    state = FlowStateModel()
    state.preferences.dry_run = True
    state.interview.core_problem = "X"
    state.interview.ten_x_vision = "Y"
    state.interview.research_focus = "Z"

    run_pipeline(state, tmp_path)

    # 1. get_context called exactly once (zero allowed only if query is empty,
    #    but with X/Y/Z interview seeded it must fire)
    assert get_context_calls["n"] == 1, (
        f"expected exactly 1 call to MemoryStore.get_context, got {get_context_calls['n']} "
        f"with queries: {get_context_calls['queries']}"
    )
    assert "X" in get_context_calls["queries"][0]
    assert "Y" in get_context_calls["queries"][0]
    assert "Z" in get_context_calls["queries"][0]

    # 2. Every adapter received the prior_knowledge kwarg
    assert "research" in init_records
    assert "strategy" in init_records
    assert "gsd" in init_records
    assert "prior_knowledge" in init_records["research"]
    assert "prior_knowledge" in init_records["strategy"]
    assert "prior_knowledge" in init_records["gsd"]

    # 3. All three received the SAME value (identity == equality for a str)
    assert (
        init_records["research"]["prior_knowledge"]
        == init_records["strategy"]["prior_knowledge"]
        == init_records["gsd"]["prior_knowledge"]
    )


def test_pipeline_empty_interview_skips_memory_lookup(tmp_path: Path, monkeypatch):
    """When interview is empty, no _pk_query is built, so get_context is never called.

    Covers the `if _pk_query else ""` branch in run_pipeline (coverage gate).
    """
    from flowstate.memory import MemoryStore

    call_count = {"n": 0}

    def spy_get_context(self, query, *, max_tokens: int = 2000):
        call_count["n"] += 1
        return ""

    monkeypatch.setattr(MemoryStore, "get_context", spy_get_context)

    state = FlowStateModel()
    state.preferences.dry_run = True
    # Leave interview fields blank — _pk_query will be empty

    run_pipeline(state, tmp_path)

    assert call_count["n"] == 0, (
        f"expected 0 calls to get_context with empty interview, got {call_count['n']}"
    )
