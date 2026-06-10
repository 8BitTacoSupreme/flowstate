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


def test_summarize_trends():
    mk = lambda i, s: JudgeResult(i, s, "")  # noqa: E731
    assert summarize([mk(0, 4), mk(1, 8)])["trend"] == "improving"
    assert summarize([mk(0, 8), mk(1, 4)])["trend"] == "declining"
    assert summarize([mk(0, 6), mk(1, 6)])["trend"] == "flat"
    assert summarize([mk(0, 5)])["trend"] == "insufficient-data"
    assert summarize([mk(0, None), mk(1, None)])["trend"] == "insufficient-data"


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
