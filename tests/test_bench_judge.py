"""Tests for the Tier-2 output-quality judge (bench/judge.py)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import bench.judge as judge_mod
from bench.judge import JudgeResult, collect_artifacts, judge_run, summarize
from bench.report import write_json


def test_parse_score_plain():
    assert judge_mod._parse_score('{"score": 7, "rationale": "ok"}') == (7.0, "ok")


def test_parse_score_embedded_in_prose():
    out = 'Here is my verdict.\n{"score": 9, "rationale": "grounded"}\nThanks!'
    assert judge_mod._parse_score(out) == (9.0, "grounded")


def test_parse_score_bool_and_missing_reject():
    assert judge_mod._parse_score('{"score": true}') == (None, "")
    assert judge_mod._parse_score("no json here") == (None, "")
    assert judge_mod._parse_score('{"nope": 1}') == (None, "")


def test_collect_artifacts_reads_and_truncates(tmp_path: Path):
    (tmp_path / "research").mkdir()
    (tmp_path / "research" / "report.md").write_text("R" * 10)
    (tmp_path / "research" / "strategy.md").write_text("S" * 10)
    blob = collect_artifacts(tmp_path)
    assert "report.md" in blob and "strategy.md" in blob
    assert len(collect_artifacts(tmp_path)) <= judge_mod._MAX_ARTIFACT_CHARS


def test_collect_artifacts_missing_never_raises(tmp_path: Path):
    assert collect_artifacts(tmp_path) == ""


def test_judge_run_no_bridge_returns_none(monkeypatch):
    monkeypatch.setattr(judge_mod, "_locate_claude", lambda: None)
    r = judge_run(0, "some artifacts", {"system_contract": "x"})
    assert r.score is None and r.run_index == 0


def test_judge_run_no_artifacts_returns_none(monkeypatch):
    monkeypatch.setattr(judge_mod, "_locate_claude", lambda: "/bin/claude")
    assert judge_run(1, "   ", {}).score is None


def test_judge_run_parses_subprocess_score(monkeypatch):
    monkeypatch.setattr(judge_mod, "_locate_claude", lambda: "/bin/claude")

    class _P:
        stdout = '{"score": 8, "rationale": "specific"}'

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _P())
    r = judge_run(2, "artifacts text", {"retrieval_questions": ["q"]})
    assert r.score == 8.0 and "specific" in r.rationale


def test_judge_run_subprocess_error_never_raises(monkeypatch):
    monkeypatch.setattr(judge_mod, "_locate_claude", lambda: "/bin/claude")

    def _boom(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(subprocess, "run", _boom)
    assert judge_run(0, "x", {}).score is None  # degrades, no raise


# ---------------------------------------------------------------------------
# Bounded retry tests (judge_run calls subprocess up to _JUDGE_MAX_ATTEMPTS)
# ---------------------------------------------------------------------------


def test_judge_run_bad_then_good_returns_score_at_2_calls(monkeypatch):
    """bad-then-good: score returned, exactly 2 subprocess.run calls made."""
    from unittest.mock import Mock

    monkeypatch.setattr(judge_mod, "_locate_claude", lambda: "/bin/claude")

    call_count = Mock()

    class _Bad:
        stdout = "not json"

    class _Good:
        stdout = '{"score": 7, "rationale": "looks good"}'

    responses = [_Bad(), _Good()]

    def _fake_run(*a, **k):
        call_count()
        return responses.pop(0)

    monkeypatch.setattr(subprocess, "run", _fake_run)
    r = judge_run(0, "artifacts", {})
    assert r.score == 7.0
    assert call_count.call_count == 2


def test_judge_run_first_try_good_exactly_1_call(monkeypatch):
    """first-try-good: exactly 1 subprocess.run call."""
    from unittest.mock import Mock

    monkeypatch.setattr(judge_mod, "_locate_claude", lambda: "/bin/claude")

    call_count = Mock()

    class _Good:
        stdout = '{"score": 9, "rationale": "excellent"}'

    def _fake_run(*a, **k):
        call_count()
        return _Good()

    monkeypatch.setattr(subprocess, "run", _fake_run)
    r = judge_run(0, "artifacts", {})
    assert r.score == 9.0
    assert call_count.call_count == 1


def test_judge_run_all_bad_3_attempts_score_none(monkeypatch):
    """all-bad over 3 attempts → score is None after exactly 3 subprocess.run calls."""
    from unittest.mock import Mock

    monkeypatch.setattr(judge_mod, "_locate_claude", lambda: "/bin/claude")

    call_count = Mock()

    class _Bad:
        stdout = "garbage output"

    def _fake_run(*a, **k):
        call_count()
        return _Bad()

    monkeypatch.setattr(subprocess, "run", _fake_run)
    r = judge_run(0, "artifacts", {})
    assert r.score is None
    assert call_count.call_count == judge_mod._JUDGE_MAX_ATTEMPTS


def test_judge_run_subprocess_raises_then_good_returns_score(monkeypatch):
    """subprocess raising on attempt 1 counts as failed; attempt 2 good → score returned."""
    from unittest.mock import Mock

    monkeypatch.setattr(judge_mod, "_locate_claude", lambda: "/bin/claude")

    call_count = Mock()
    attempts: list = [True]  # True = raise on first call

    class _Good:
        stdout = '{"score": 6, "rationale": "recovered"}'

    def _fake_run(*a, **k):
        call_count()
        if attempts:
            attempts.pop()
            raise RuntimeError("transient error")
        return _Good()

    monkeypatch.setattr(subprocess, "run", _fake_run)
    r = judge_run(0, "artifacts", {})
    assert r.score == 6.0
    assert call_count.call_count == 2


def test_judge_run_early_return_no_subprocess_calls(monkeypatch):
    """Early-return (no claude / no artifacts) → 0 subprocess calls."""
    from unittest.mock import Mock

    call_count = Mock()

    # No bridge
    monkeypatch.setattr(judge_mod, "_locate_claude", lambda: None)
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: call_count())
    r = judge_run(0, "artifacts", {})
    assert r.score is None
    assert call_count.call_count == 0

    # No artifacts
    monkeypatch.setattr(judge_mod, "_locate_claude", lambda: "/bin/claude")
    r2 = judge_run(0, "   ", {})
    assert r2.score is None
    assert call_count.call_count == 0


# ---------------------------------------------------------------------------
# Independence guard + CLI (IND-01)
# ---------------------------------------------------------------------------


def test_validate_judges_empty_raises():
    import pytest

    with pytest.raises(ValueError):
        judge_mod._validate_judges([], "opus")


def test_validate_judges_same_model_raises():
    import pytest

    with pytest.raises(ValueError):
        judge_mod._validate_judges(["opus"], "opus")


def test_validate_judges_any_judge_equals_producer_raises():
    """ANY judge == producer is a hard fail, not just the aggregate (D-07)."""
    import pytest

    with pytest.raises(ValueError):
        judge_mod._validate_judges(["sonnet", "opus"], "opus")


def test_validate_judges_all_distinct_ok():
    assert judge_mod._validate_judges(["sonnet", "haiku"], "opus") is None


def test_main_absent_judge_model_nonzero():
    assert judge_mod.main(["--producer-model", "opus"]) != 0


def test_main_same_model_nonzero():
    assert judge_mod.main(["--judge-model", "opus", "--producer-model", "opus"]) != 0


def test_main_distinct_model_zero():
    assert judge_mod.main(["--judge-model", "sonnet", "--producer-model", "opus"]) == 0


def test_main_multi_judge_one_equals_producer_nonzero():
    assert judge_mod.main(["--judge-model", "sonnet,opus", "--producer-model", "opus"]) != 0


def test_guard_does_not_touch_judge_run_neverraise(monkeypatch):
    """judge_run still returns its parsed score unchanged — the guard did not
    add any raise into the per-run never-raise path (D-03)."""
    monkeypatch.setattr(judge_mod, "_locate_claude", lambda: "/bin/claude")

    class _P:
        stdout = '{"score": 8, "rationale": "specific"}'

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _P())
    r = judge_run(2, "artifacts text", {"retrieval_questions": ["q"]})
    assert r.score == 8.0


def test_summarize_trends():
    mk = lambda i, s: JudgeResult(i, s, "")  # noqa: E731
    assert summarize([mk(0, 4), mk(1, 8)])["trend"] == "improving"
    assert summarize([mk(0, 8), mk(1, 4)])["trend"] == "declining"
    assert summarize([mk(0, 6), mk(1, 6)])["trend"] == "flat"
    assert summarize([mk(0, 5)])["trend"] == "insufficient-data"
    assert summarize([mk(0, None), mk(1, None)])["trend"] == "insufficient-data"


# ---------------------------------------------------------------------------
# Multi-judge aggregation (IND-02)
# ---------------------------------------------------------------------------


def test_pass_threshold_constant_exists():
    assert isinstance(judge_mod._PASS_THRESHOLD, float)


def test_aggregate_two_all_pass_mean_and_wilson():
    agg = judge_mod.aggregate_judges([JudgeResult(0, 8, ""), JudgeResult(1, 9, "")])
    assert agg["mean"] == 8.5
    assert agg["median"] == 8.5
    assert agg["pass_rate"] == 1.0
    assert agg["majority_pass"] is True
    assert 0.0 <= agg["wilson_low"] <= agg["wilson_high"] <= 1.0


def test_aggregate_three_majority_pass():
    agg = judge_mod.aggregate_judges(
        [JudgeResult(0, 6, ""), JudgeResult(1, 8, ""), JudgeResult(2, 9, "")]
    )
    assert agg["passes"] == 2
    assert agg["majority_pass"] is True
    assert round(agg["pass_rate"], 3) == 0.667


def test_aggregate_even_n_tie_is_fail():
    """2 pass / 4 total is a tie, not a majority -> majority_pass False (D-08)."""
    agg = judge_mod.aggregate_judges(
        [
            JudgeResult(0, 8, ""),
            JudgeResult(1, 9, ""),
            JudgeResult(2, 5, ""),
            JudgeResult(3, 4, ""),
        ]
    )
    assert agg["passes"] == 2
    assert agg["n_scored"] == 4
    assert agg["pass_rate"] == 0.5
    assert agg["majority_pass"] is False


def test_aggregate_none_excluded_from_denominator():
    """A None (insufficient-data) score is excluded from the pass-rate denominator."""
    agg = judge_mod.aggregate_judges(
        [JudgeResult(0, 8, ""), JudgeResult(1, 9, ""), JudgeResult(2, None, "")]
    )
    assert agg["n_judges"] == 3
    assert agg["n_scored"] == 2  # None excluded
    assert agg["pass_rate"] == 1.0
    assert agg["majority_pass"] is True


def test_aggregate_all_none_never_raises():
    agg = judge_mod.aggregate_judges([JudgeResult(0, None, ""), JudgeResult(1, None, "")])
    assert agg["n_scored"] == 0
    assert agg["mean"] is None
    assert agg["pass_rate"] is None
    assert agg["majority_pass"] is False


def test_aggregate_single_judge_backward_compatible():
    agg = judge_mod.aggregate_judges([JudgeResult(0, 9, "")])
    assert agg["mean"] == 9.0
    assert agg["pass_rate"] == 1.0
    assert agg["majority_pass"] is True


def test_summarize_unchanged_for_fixed_input():
    """Regression guard (D-02): summarize output is byte-identical to the known shape."""
    results = [JudgeResult(0, 4, ""), JudgeResult(1, 8, "")]
    assert summarize(results) == {
        "scores": [4, 8],
        "trend": "improving",
        "first": 4,
        "last": 8,
        "delta": 4,
    }


def test_write_json_includes_judge_when_present(tmp_path: Path):
    from bench.metrics import compute_scorecard

    sc = compute_scorecard([])
    out = tmp_path / "r.json"
    write_json(sc, out, judge_results=[JudgeResult(0, 5.0, "a"), JudgeResult(1, 8.0, "b")])
    text = out.read_text()
    assert '"judge"' in text and '"trend": "improving"' in text


def test_write_json_omits_judge_when_absent(tmp_path: Path):
    from bench.metrics import compute_scorecard

    out = tmp_path / "r.json"
    write_json(compute_scorecard([]), out)
    assert '"judge"' not in out.read_text()


def test_run_one_inject_off_suppresses_and_restores(monkeypatch, tmp_path):
    """Control arm: inject=False makes build_context_prefix return '' during the run,
    then restores it — memory still accumulates, but the LLM sees no prior knowledge.
    LEGACY test — kept to verify backward compat is NOT broken (inject kwarg removed).
    """
    import flowstate.orchestrator as orch
    import flowstate.state as fstate
    from bench import compound_eval as ce

    orig = orch.build_context_prefix
    seen = {}

    class _Prefs:
        dry_run = False

    class _State:
        preferences = _Prefs()

    monkeypatch.setattr(fstate, "load_state", lambda root: _State())
    monkeypatch.setattr(
        orch, "run_pipeline", lambda s, r: seen.update(p=orch.build_context_prefix(r, None, "q"))
    )

    # After migration inject= is removed; layers="none" is the equivalent.
    ce._run_one(tmp_path, dry_run=False, layers="none")
    assert seen["p"] == ""  # injection suppressed during the run
    assert orch.build_context_prefix is orig  # restored after


def _make_stub_state_and_run_pipeline(monkeypatch, seen: dict):
    """Patch load_state and run_pipeline; run_pipeline records orch.build_context_prefix result."""
    import flowstate.orchestrator as orch
    import flowstate.state as fstate

    class _Prefs:
        dry_run = False

    class _State:
        preferences = _Prefs()

    monkeypatch.setattr(fstate, "load_state", lambda root: _State())
    monkeypatch.setattr(
        orch, "run_pipeline", lambda s, r: seen.update(p=orch.build_context_prefix(r, None, "q"))
    )


def test_run_one_layers_full_no_patch(monkeypatch, tmp_path):
    """full arm: orch.build_context_prefix is NOT patched during run and is orig after."""
    import flowstate.orchestrator as orch
    from bench import compound_eval as ce

    orig = orch.build_context_prefix
    seen_during: list = []
    seen = {}

    def _fake_pipeline(s, r):
        seen_during.append(orch.build_context_prefix is orig)
        seen["p"] = "not-empty"  # full arm — prefix not suppressed

    import flowstate.state as fstate

    class _Prefs:
        dry_run = False

    class _State:
        preferences = _Prefs()

    monkeypatch.setattr(fstate, "load_state", lambda root: _State())
    monkeypatch.setattr(orch, "run_pipeline", _fake_pipeline)

    ce._run_one(tmp_path, dry_run=False, layers="full")
    assert seen_during == [True], "full arm must NOT patch build_context_prefix during run"
    assert orch.build_context_prefix is orig, "build_context_prefix must be orig after full arm"


def test_run_one_layers_none_empty_prefix(monkeypatch, tmp_path):
    """none arm: wrapper injects include_layers=frozenset() → empty prefix; patch restored after."""
    import flowstate.orchestrator as orch
    from bench import compound_eval as ce
    from bench.compound_eval import _LAYERS_MAP

    orig = orch.build_context_prefix
    seen = {}

    # Provide a real-ish build_context_prefix that honors include_layers
    def _fake_bcp(root, memory, query, **kwargs):
        include = kwargs.get("include_layers")
        if include is not None and len(include) == 0:
            return ""
        return "some-prefix"

    orch.build_context_prefix = _fake_bcp
    try:
        import flowstate.state as fstate

        class _Prefs:
            dry_run = False

        class _State:
            preferences = _Prefs()

        monkeypatch.setattr(fstate, "load_state", lambda root: _State())
        monkeypatch.setattr(
            orch,
            "run_pipeline",
            lambda s, r: seen.update(p=orch.build_context_prefix(r, None, "q")),
        )

        ce._run_one(tmp_path, dry_run=False, layers="none")
        assert seen["p"] == "", "none arm: prefix must be empty (include_layers=frozenset())"
        assert _LAYERS_MAP["none"] == frozenset()
    finally:
        orch.build_context_prefix = orig

    assert orch.build_context_prefix is orig, "build_context_prefix must be restored after none arm"


def test_run_one_layers_pack_selects_rag(monkeypatch, tmp_path):
    """pack arm: wrapper injects include_layers=frozenset({'fixtures','pack'}); patch restored."""
    import flowstate.orchestrator as orch
    from bench import compound_eval as ce
    from bench.compound_eval import _LAYERS_MAP

    orig = orch.build_context_prefix
    seen = {}

    def _fake_bcp(root, memory, query, **kwargs):
        seen["include_layers"] = kwargs.get("include_layers")
        return "pack-prefix"

    orch.build_context_prefix = _fake_bcp
    try:
        import flowstate.state as fstate

        class _Prefs:
            dry_run = False

        class _State:
            preferences = _Prefs()

        monkeypatch.setattr(fstate, "load_state", lambda root: _State())
        monkeypatch.setattr(
            orch,
            "run_pipeline",
            lambda s, r: seen.update(p=orch.build_context_prefix(r, None, "q")),
        )

        ce._run_one(tmp_path, dry_run=False, layers="pack")
        assert seen.get("include_layers") == _LAYERS_MAP["pack"], (
            "pack arm: include_layers must be frozenset({'fixtures','pack'})"
        )
    finally:
        orch.build_context_prefix = orig

    assert orch.build_context_prefix is orig, "build_context_prefix must be restored after pack arm"


def test_run_one_layers_memory_selects_compounding(monkeypatch, tmp_path):
    """memory arm: wrapper injects include_layers=frozenset({'gotchas','memory','since_last_run'})."""
    import flowstate.orchestrator as orch
    from bench import compound_eval as ce
    from bench.compound_eval import _LAYERS_MAP

    orig = orch.build_context_prefix
    seen = {}

    def _fake_bcp(root, memory, query, **kwargs):
        seen["include_layers"] = kwargs.get("include_layers")
        return "memory-prefix"

    orch.build_context_prefix = _fake_bcp
    try:
        import flowstate.state as fstate

        class _Prefs:
            dry_run = False

        class _State:
            preferences = _Prefs()

        monkeypatch.setattr(fstate, "load_state", lambda root: _State())
        monkeypatch.setattr(
            orch,
            "run_pipeline",
            lambda s, r: seen.update(p=orch.build_context_prefix(r, None, "q")),
        )

        ce._run_one(tmp_path, dry_run=False, layers="memory")
        assert seen.get("include_layers") == _LAYERS_MAP["memory"], (
            "memory arm: include_layers must be frozenset({'gotchas','memory','since_last_run'})"
        )
    finally:
        orch.build_context_prefix = orig

    assert orch.build_context_prefix is orig, (
        "build_context_prefix must be restored after memory arm"
    )
