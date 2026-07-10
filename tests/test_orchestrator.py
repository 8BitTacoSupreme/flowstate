"""Tests for FlowState orchestrator — dry-run pipeline."""

from pathlib import Path

from flowstate.orchestrator import _make_bridge, run_pipeline
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

    # Healthy repo so Discipline's required-set (git_repo AND pytest_config) passes.
    (tmp_path / ".git").mkdir()
    (tmp_path / "pyproject.toml").write_text("[tool.pytest]")

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


class TestMakeBridgeAllowedTools:
    def test_mcp_repomix_in_allowed_tools(self, tmp_path: Path):
        """_make_bridge always grants mcp__repomix to spawned agents (PACK-03)."""
        bridge = _make_bridge(tmp_path, dry_run=True)
        assert "mcp__repomix" in bridge.config.allowed_tools

    def test_mcp_repomix_with_preferences(self, tmp_path: Path):
        """mcp__repomix is granted even when preferences override model/budget/effort."""
        state = FlowStateModel()
        state.preferences.model = "claude-3-sonnet"
        state.preferences.max_budget_usd = 1.0
        state.preferences.effort = "low"

        bridge = _make_bridge(tmp_path, dry_run=True, preferences=state.preferences)
        assert "mcp__repomix" in bridge.config.allowed_tools

    def test_prompt_caching_true_threads_into_bridge(self, tmp_path: Path):
        """preferences.enable_prompt_caching_1h=True is reflected in bridge config."""
        state = FlowStateModel()
        state.preferences.enable_prompt_caching_1h = True

        bridge = _make_bridge(tmp_path, dry_run=True, preferences=state.preferences)
        assert bridge.config.enable_prompt_caching_1h is True

    def test_prompt_caching_false_threads_into_bridge(self, tmp_path: Path):
        """preferences.enable_prompt_caching_1h=False is reflected in bridge config."""
        state = FlowStateModel()
        state.preferences.enable_prompt_caching_1h = False

        bridge = _make_bridge(tmp_path, dry_run=True, preferences=state.preferences)
        assert bridge.config.enable_prompt_caching_1h is False

    def test_no_preferences_leaves_bridge_default_false(self, tmp_path: Path):
        """_make_bridge with no preferences leaves BridgeConfig at its default False."""
        bridge = _make_bridge(tmp_path, dry_run=True)
        assert bridge.config.enable_prompt_caching_1h is False


def test_build_context_prefix_called_once_and_byte_identical_across_adapters(
    tmp_path: Path, monkeypatch
):
    """build_context_prefix() is called exactly once; all 3 adapters receive the same string.

    Verifies CAG-01 / CAG-03: the orchestrator builds the layered prefix once and
    threads the byte-identical result into ResearchAdapter, StrategyAdapter, and
    GSDAdapter via the prior_knowledge seam.
    """
    from flowstate.context_prefix import build_context_prefix
    from flowstate.tools.gsd_adapter import GSDAdapter
    from flowstate.tools.research import ResearchAdapter
    from flowstate.tools.strategy import StrategyAdapter

    # Spy on build_context_prefix — count calls, capture return value
    build_calls = {"n": 0, "last_result": None}
    original_bcp = build_context_prefix

    def spy_build_context_prefix(root, memory, query, **kwargs):
        build_calls["n"] += 1
        result = original_bcp(root, memory, query, **kwargs)
        build_calls["last_result"] = result
        return result

    monkeypatch.setattr("flowstate.orchestrator.build_context_prefix", spy_build_context_prefix)

    # Record prior_knowledge value each adapter receives
    init_records: dict[str, str | None] = {}

    def make_recording_init(cls, name):
        original_init = cls.__init__

        def recording_init(self, *args, **kwargs):
            init_records[name] = kwargs.get("prior_knowledge")
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
    state.interview.core_problem = "A"
    state.interview.ten_x_vision = "B"
    state.interview.research_focus = "C"

    run_pipeline(state, tmp_path)

    # build_context_prefix called exactly once
    assert build_calls["n"] == 1, f"Expected 1 call to build_context_prefix, got {build_calls['n']}"

    # All three adapters received prior_knowledge
    for adapter in ("research", "strategy", "gsd"):
        assert adapter in init_records, f"{adapter} adapter not recorded"
        assert (
            "prior_knowledge" in (str(type(init_records[adapter])))
            or init_records[adapter] is not None
            or init_records[adapter] == ""
        ), f"{adapter} must receive prior_knowledge kwarg"

    # All three received the SAME byte-identical string
    assert init_records["research"] == init_records["strategy"] == init_records["gsd"], (
        "All adapters must receive byte-identical prior_knowledge string"
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


def test_run_pipeline_writes_run_journal_entry(tmp_path: Path):
    """append_run_entry must be called once per pipeline run."""
    from unittest.mock import patch

    state = FlowStateModel()
    state.preferences.dry_run = True

    with patch("flowstate.orchestrator.append_run_entry") as mock_journal:
        run_pipeline(state, tmp_path)

    assert mock_journal.call_count == 1
    # run_id must be a 12-char hex string (third positional arg)
    call_run_id = mock_journal.call_args.args[2]
    assert len(call_run_id) == 12
    assert call_run_id.isalnum()


def test_run_pipeline_journal_entry_lands_in_memory_db(tmp_path: Path):
    """After a dry-run pipeline, exactly one MemoryKind.RUN entry exists in memory.db."""
    from flowstate.memory import MemoryKind, MemoryStore

    state = FlowStateModel()
    state.preferences.dry_run = True

    run_pipeline(state, tmp_path)

    with MemoryStore(root=tmp_path) as store:
        assert store.count(MemoryKind.RUN) == 1


def test_run_pipeline_calls_harvest_planning_gotchas_once(tmp_path: Path, monkeypatch):
    """harvest_planning_gotchas is called exactly once after memory opens, before adapters."""
    from unittest.mock import patch

    call_log: list[str] = []

    def fake_harvest(memory, root):
        call_log.append("harvest")

    state = FlowStateModel()
    state.preferences.dry_run = True

    with patch("flowstate.gotchas.harvest_planning_gotchas", side_effect=fake_harvest):
        run_pipeline(state, tmp_path)

    assert call_log.count("harvest") == 1


def test_run_pipeline_harvest_failure_does_not_abort(tmp_path: Path, monkeypatch):
    """If harvest_planning_gotchas raises, run_pipeline completes normally."""
    from unittest.mock import patch

    from flowstate.state import ToolStatus

    def exploding_harvest(memory, root):
        raise RuntimeError("harvest exploded")

    state = FlowStateModel()
    state.preferences.dry_run = True

    # Healthy repo so Discipline's required-set (git_repo AND pytest_config) passes.
    (tmp_path / ".git").mkdir()
    (tmp_path / "pyproject.toml").write_text("[tool.pytest]")

    with patch("flowstate.gotchas.harvest_planning_gotchas", side_effect=exploding_harvest):
        result = run_pipeline(state, tmp_path)

    # Pipeline still completed all tools
    for name, ts in result.tools.items():
        assert ts.status == ToolStatus.COMPLETED, f"{name} not completed: {ts.status}"


def test_discipline_blocks_on_unhealthy_repo(tmp_path: Path):
    """A bare repo (no .git, no pytest config) makes Discipline BLOCKED, not COMPLETED."""
    state = FlowStateModel()
    state.preferences.dry_run = True

    result = run_pipeline(state, tmp_path)

    assert result.tools["discipline"].status == ToolStatus.BLOCKED
    assert result.tools["discipline"].error is not None

    blocked = sum(1 for ts in result.tools.values() if ts.status == ToolStatus.BLOCKED)
    assert blocked >= 1
