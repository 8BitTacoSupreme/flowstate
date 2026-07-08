"""Tests for bench/longmemeval_qa.py — offline QA-accuracy harness tests.

All tests are offline: every LLM, embedder, and ranker is monkeypatched on
its owning module so no real claude binary or fastembed is invoked.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

import bench.longmemeval_qa as qa

_FIXTURE = Path(__file__).parent.parent / "bench" / "fixtures" / "lme_smoke.json"


# ─────────────────────────────────────────────────────────────────────────────
# Inline fixture helpers
# ─────────────────────────────────────────────────────────────────────────────


def _make_instances(n_single: int, n_multi: int) -> list[dict]:
    """Build inline LME instances without real haystack sessions."""
    instances: list[dict] = []
    for i in range(n_single):
        instances.append(
            {
                "question_id": f"ss-{i}",
                "question_type": "single_session",
                "question": f"Q single {i}",
                "answer": f"A single {i}",
                "question_date": "2024-01-01",
                "haystack_session_ids": [f"sess-{i}"],
                "haystack_sessions": [[{"role": "user", "content": f"content {i}"}]],
                "answer_session_ids": [f"sess-{i}"],
            }
        )
    for i in range(n_multi):
        instances.append(
            {
                "question_id": f"ms-{i}",
                "question_type": "multi_session",
                "question": f"Q multi {i}",
                "answer": f"A multi {i}",
                "question_date": "2024-01-01",
                "haystack_session_ids": [f"msess-{i}a", f"msess-{i}b"],
                "haystack_sessions": [
                    [{"role": "user", "content": f"mc {i}a"}],
                    [{"role": "user", "content": f"mc {i}b"}],
                ],
                "answer_session_ids": [f"msess-{i}a", f"msess-{i}b"],
            }
        )
    return instances


def _make_args(
    tmp_path: Path,
    *,
    backend: str = "bm25",
    arms: str = "retrieval",
    k: int = 5,
    limit: int | None = None,
    reader_model: str = "sonnet",
    judge_model: str = "sonnet",
    char_budget: int = 48000,
) -> argparse.Namespace:
    """Build an argparse.Namespace mimicking _build_parser() output."""
    return argparse.Namespace(
        backend=backend,
        arms=arms,
        k=k,
        limit=limit,
        reader_model=reader_model,
        judge_model=judge_model,
        embed_model="BAAI/bge-small-en-v1.5",
        char_budget=char_budget,
        out=tmp_path / "out.json",
    )


# ─────────────────────────────────────────────────────────────────────────────
# _reader_context tests
# ─────────────────────────────────────────────────────────────────────────────


def test_reader_context_separates_and_orders():
    """_reader_context joins selected texts in requested id order, separated by separator."""
    docs = [("a", "text-a"), ("b", "text-b"), ("c", "text-c")]
    result = qa._reader_context(docs, ["c", "a"])
    assert result == "text-c\n\n---\n\ntext-a"


def test_reader_context_respects_char_budget():
    """char_budget truncates the result to at most char_budget characters."""
    docs = [("a", "x" * 100), ("b", "y" * 100)]
    result = qa._reader_context(docs, ["a", "b"], char_budget=50)
    assert len(result) <= 50


def test_reader_context_empty_ids_returns_empty():
    """Empty ids list produces an empty string."""
    docs = [("a", "text-a")]
    assert qa._reader_context(docs, []) == ""


def test_reader_context_never_raises():
    """Malformed or None docs returns empty string without raising."""
    result = qa._reader_context(None, ["a"])  # type: ignore[arg-type]
    assert result == ""


# ─────────────────────────────────────────────────────────────────────────────
# _judge_one tests
# ─────────────────────────────────────────────────────────────────────────────


def test_judge_one_passthrough(monkeypatch):
    """_judge_one passes _factcheck result through for True, False, and None."""
    import bench.grounding as _g

    instance = {"question_type": "single_session", "answer": "gold answer"}

    for expected in (True, False, None):
        monkeypatch.setattr(_g, "_factcheck", lambda a, gt, m, _e=expected: _e)
        result = qa._judge_one("my answer", instance, "sonnet")
        assert result is expected


# ─────────────────────────────────────────────────────────────────────────────
# _run_qa tests
# ─────────────────────────────────────────────────────────────────────────────


def test_run_qa_retrieval_per_type_and_overall(tmp_path, monkeypatch):
    """_run_qa with bm25/retrieval reports per-type AND overall accuracy with Wilson CIs."""
    import bench._retrieval as _r
    import bench.grounding as _g
    import bench.longmemeval as _lme

    # 2 single_session + 1 multi_session
    instances = _make_instances(n_single=2, n_multi=1)
    args = _make_args(tmp_path, backend="bm25", arms="retrieval")

    fixed_docs = [("s", "some session text")]
    monkeypatch.setattr(_lme, "_build_docs", lambda inst: fixed_docs)
    monkeypatch.setattr(_r, "bm25_rank", lambda docs, q, k: ["s"])
    monkeypatch.setattr(_g, "_answer", lambda prefix, question, model, **kw: "the answer")

    # single_session: first 2 calls → True (correct); multi_session: 3rd call → False
    call_count = [0]

    def side_effect(answer, gt, model):
        call_count[0] += 1
        return call_count[0] <= 2

    monkeypatch.setattr(_g, "_factcheck", side_effect)

    rc = qa._run_qa(args, instances)
    assert isinstance(rc, int)

    result = json.loads(args.out.read_text())
    arm = result["arms"]["retrieval"]

    ss = arm["by_type"]["single_session"]
    ms = arm["by_type"]["multi_session"]
    overall = arm["overall"]

    assert ss["accuracy"] == pytest.approx(1.0)
    assert ss["n"] == 2
    assert ms["accuracy"] == pytest.approx(0.0)
    assert ms["n"] == 1
    assert overall["accuracy"] == pytest.approx(2 / 3)
    assert overall["n"] == 3
    assert len(ss["wilson_ci"]) == 2
    assert len(ms["wilson_ci"]) == 2
    assert len(overall["wilson_ci"]) == 2


def test_run_qa_oracle_uses_answer_session_ids(tmp_path, monkeypatch):
    """Oracle arm builds context from instance['answer_session_ids'], not from ranking."""
    import bench.grounding as _g
    import bench.longmemeval as _lme

    instances = _make_instances(n_single=1, n_multi=0)
    args = _make_args(tmp_path, backend="bm25", arms="oracle")

    # Spy on _reader_context to capture which ids are passed
    captured_ids: list[str] = []
    original_reader_context = qa._reader_context

    def spy_reader_context(docs, ids, **kw):
        captured_ids.extend(ids)
        return original_reader_context(docs if docs is not None else [], ids, **kw)

    monkeypatch.setattr(qa, "_reader_context", spy_reader_context)
    monkeypatch.setattr(_lme, "_build_docs", lambda inst: [("sess-0", "session text")])
    monkeypatch.setattr(_g, "_answer", lambda prefix, question, model, **kw: "answer")
    monkeypatch.setattr(_g, "_factcheck", lambda a, gt, m: True)

    assert isinstance(qa._run_qa(args, instances), int)

    # The oracle arm must have called _reader_context with answer_session_ids
    expected_id = instances[0]["answer_session_ids"][0]
    assert expected_id in captured_ids, f"expected {expected_id!r} in {captured_ids!r}"

    result = json.loads(args.out.read_text())
    oracle = result["arms"]["oracle"]
    assert oracle["overall"]["accuracy"] == pytest.approx(1.0)
    assert oracle["overall"]["n"] == 1


def test_run_qa_limit_caps_instances(tmp_path, monkeypatch):
    """--limit=2 over 4 instances scores exactly 2; output records limit==2."""
    import bench._retrieval as _r
    import bench.grounding as _g
    import bench.longmemeval as _lme

    instances = _make_instances(n_single=4, n_multi=0)
    args = _make_args(tmp_path, backend="bm25", arms="retrieval", limit=2)

    monkeypatch.setattr(_lme, "_build_docs", lambda inst: [("s", "text")])
    monkeypatch.setattr(_r, "bm25_rank", lambda docs, q, k: ["s"])
    monkeypatch.setattr(_g, "_answer", lambda prefix, question, model, **kw: "answer")
    monkeypatch.setattr(_g, "_factcheck", lambda a, gt, m: True)

    qa._run_qa(args, instances)

    result = json.loads(args.out.read_text())
    assert result["limit"] == 2
    assert result["arms"]["retrieval"]["overall"]["n"] == 2


def test_run_qa_none_judge_counts_incorrect_but_in_n(tmp_path, monkeypatch):
    """None judge result is incorrect but tallied in n; accuracy == 0.5 over n==2."""
    import bench._retrieval as _r
    import bench.grounding as _g
    import bench.longmemeval as _lme

    instances = _make_instances(n_single=2, n_multi=0)
    args = _make_args(tmp_path, backend="bm25", arms="retrieval")

    monkeypatch.setattr(_lme, "_build_docs", lambda inst: [("s", "text")])
    monkeypatch.setattr(_r, "bm25_rank", lambda docs, q, k: ["s"])
    monkeypatch.setattr(_g, "_answer", lambda prefix, question, model, **kw: "answer")

    call_count = [0]

    def none_then_true(answer, gt, model):
        call_count[0] += 1
        return None if call_count[0] == 1 else True

    monkeypatch.setattr(_g, "_factcheck", none_then_true)

    assert isinstance(qa._run_qa(args, instances), int)

    result = json.loads(args.out.read_text())
    overall = result["arms"]["retrieval"]["overall"]
    assert overall["n"] == 2
    assert overall["accuracy"] == pytest.approx(0.5)


def test_run_qa_returns_one_when_zero_scored(tmp_path):
    """Empty instance list -> _run_qa returns 1 (zero instances scored)."""
    args = _make_args(tmp_path, backend="bm25", arms="retrieval")
    rc = qa._run_qa(args, [])
    assert rc == 1


def test_run_qa_malformed_instance_skipped_no_crash(tmp_path, monkeypatch):
    """Instance where _build_docs returns None is skipped; no exception; rc is int."""
    import bench.grounding as _g
    import bench.longmemeval as _lme

    instances = _make_instances(n_single=1, n_multi=0)
    args = _make_args(tmp_path, backend="bm25", arms="retrieval")

    monkeypatch.setattr(_lme, "_build_docs", lambda inst: None)
    monkeypatch.setattr(_g, "_answer", lambda prefix, question, model, **kw: "answer")
    monkeypatch.setattr(_g, "_factcheck", lambda a, gt, m: True)

    rc = qa._run_qa(args, instances)
    assert isinstance(rc, int)


# ─────────────────────────────────────────────────────────────────────────────
# main() e2e tests
# ─────────────────────────────────────────────────────────────────────────────


def test_main_e2e_bm25_offline(tmp_path, monkeypatch):
    """main() with lme_smoke.json + bm25 + monkeypatched LLM calls -> rc=0 and valid JSON."""
    import bench.grounding as _g

    monkeypatch.setattr(_g, "_answer", lambda prefix, question, model, **kw: "some answer")
    monkeypatch.setattr(_g, "_factcheck", lambda a, gt, m: True)

    out_file = tmp_path / "qa.json"
    rc = qa.main(
        [
            "--data",
            str(_FIXTURE),
            "--backend",
            "bm25",
            "--arms",
            "retrieval,oracle",
            "--k",
            "5",
            "--limit",
            "2",
            "--out",
            str(out_file),
        ]
    )

    assert rc == 0

    result = json.loads(out_file.read_text())
    assert result["benchmark"] == "longmemeval_qa"
    assert "n_instances" in result
    assert "limit" in result
    assert "backend" in result
    assert "k" in result
    assert "reader_model" in result
    assert "judge_model" in result
    assert "arms" in result
    assert "retrieval" in result["arms"]
    assert "oracle" in result["arms"]

    for arm_name in ("retrieval", "oracle"):
        arm = result["arms"][arm_name]
        assert "overall" in arm, f"arm {arm_name!r} missing 'overall'"
        assert "by_type" in arm, f"arm {arm_name!r} missing 'by_type'"


def test_main_semantic_unavailable_does_not_raise(tmp_path, monkeypatch):
    """Semantic arm degrades gracefully when backend unavailable; returns int, no exception."""
    import bench._retrieval as _r
    import bench.grounding as _g

    monkeypatch.setattr(_r, "semantic_backend_available", lambda model: (None, False))
    monkeypatch.setattr(_g, "_answer", lambda prefix, question, model, **kw: "answer")
    monkeypatch.setattr(_g, "_factcheck", lambda a, gt, m: True)

    out_file = tmp_path / "out.json"
    rc = qa.main(
        [
            "--data",
            str(_FIXTURE),
            "--backend",
            "semantic",
            "--arms",
            "retrieval",
            "--k",
            "5",
            "--limit",
            "2",
            "--out",
            str(out_file),
        ]
    )

    assert isinstance(rc, int)
