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
    judge_provider: str = "claude",
    reader_provider: str = "claude",
    sample: int | None = None,
    seed: int = 0,
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
        judge_provider=judge_provider,
        reader_provider=reader_provider,
        sample=sample,
        seed=seed,
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


# ─────────────────────────────────────────────────────────────────────────────
# NEW: openai judge seam tests (_openai_chat → _judge_openai)
# ─────────────────────────────────────────────────────────────────────────────


def test__judge_openai_yes_true(monkeypatch):
    """_openai_chat returning 'yes' → _judge_openai returns True."""
    monkeypatch.setattr(qa, "_openai_chat", lambda model, system, user: "yes")
    result = qa._judge_openai("what color?", "blue", "blue", "gpt-4o")
    assert result is True


def test__judge_openai_no_false(monkeypatch):
    """_openai_chat returning 'no' → _judge_openai returns False."""
    monkeypatch.setattr(qa, "_openai_chat", lambda model, system, user: "no")
    result = qa._judge_openai("what color?", "blue", "red", "gpt-4o")
    assert result is False


def test__judge_openai_garbage_none(monkeypatch):
    """_openai_chat returning unparseable text → _judge_openai returns None."""
    monkeypatch.setattr(qa, "_openai_chat", lambda model, system, user: "maybe??")
    result = qa._judge_openai("what?", "gold", "ans", "gpt-4o")
    assert result is None


def test__judge_openai_returns_none_seam_none(monkeypatch):
    """_openai_chat returning None → _judge_openai returns None."""
    monkeypatch.setattr(qa, "_openai_chat", lambda model, system, user: None)
    result = qa._judge_openai("what?", "gold", "ans", "gpt-4o")
    assert result is None


def test__judge_openai_never_raises(monkeypatch):
    """_openai_chat raising → _judge_openai returns None, never raises."""

    def raise_always(model, system, user):
        raise RuntimeError("network failure")

    monkeypatch.setattr(qa, "_openai_chat", raise_always)
    result = qa._judge_openai("what?", "gold", "ans", "gpt-4o")
    assert result is None


# ─────────────────────────────────────────────────────────────────────────────
# NEW: provider routing through _judge_one
# ─────────────────────────────────────────────────────────────────────────────


def test__judge_one_routes_openai(monkeypatch):
    """provider='openai' → _judge_openai called, _g._factcheck NOT called."""
    import bench.grounding as _g

    openai_calls: list[tuple] = []
    factcheck_calls: list[tuple] = []

    monkeypatch.setattr(
        qa,
        "_judge_openai",
        lambda q, gold, ans, model: openai_calls.append((q, gold, ans, model)) or True,
    )
    monkeypatch.setattr(
        _g,
        "_factcheck",
        lambda a, gt, m: factcheck_calls.append((a, gt, m)) or True,
    )

    result = qa._judge_one(
        "ans",
        {"question_type": "single_session", "question": "q", "answer": "gold"},
        "gpt-4o",
        provider="openai",
    )

    assert len(openai_calls) == 1
    assert len(factcheck_calls) == 0
    assert result is True


def test__judge_one_routes_claude_default(monkeypatch):
    """provider defaults to 'claude' → _g._factcheck called, _judge_openai NOT called."""
    import bench.grounding as _g

    openai_calls: list[tuple] = []
    factcheck_calls: list[tuple] = []

    monkeypatch.setattr(
        qa,
        "_judge_openai",
        lambda q, gold, ans, model: openai_calls.append((q, gold, ans, model)) or False,
    )
    monkeypatch.setattr(
        _g,
        "_factcheck",
        lambda a, gt, m: factcheck_calls.append((a, gt, m)) or True,
    )

    result = qa._judge_one(
        "ans",
        {"question_type": "single_session", "question": "q", "answer": "gold"},
        "sonnet",
    )

    assert len(factcheck_calls) == 1
    assert len(openai_calls) == 0
    assert result is True


# ─────────────────────────────────────────────────────────────────────────────
# NEW: openai hard-check tests
# ─────────────────────────────────────────────────────────────────────────────


def test_run_qa_openai_missing_key_returns_one(tmp_path, monkeypatch):
    """provider='openai' with OPENAI_API_KEY unset → returns 1, no judge calls."""
    import bench._retrieval as _r
    import bench.grounding as _g
    import bench.longmemeval as _lme

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "")  # ensure absent / empty
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    factcheck_calls: list[bool] = []
    openai_judge_calls: list[bool] = []

    monkeypatch.setattr(_g, "_factcheck", lambda a, gt, m: factcheck_calls.append(True) or True)
    monkeypatch.setattr(
        qa, "_judge_openai", lambda q, gold, ans, model: openai_judge_calls.append(True) or True
    )
    monkeypatch.setattr(_lme, "_build_docs", lambda inst: [("s", "text")])
    monkeypatch.setattr(_r, "bm25_rank", lambda docs, q, k: ["s"])
    monkeypatch.setattr(_g, "_answer", lambda prefix, question, model, **kw: "ans")

    instances = _make_instances(n_single=1, n_multi=0)
    args = _make_args(tmp_path, backend="bm25", arms="retrieval", judge_provider="openai")

    rc = qa._run_qa(args, instances)

    assert rc == 1, f"expected rc=1 (hard-check), got {rc}"
    assert len(factcheck_calls) == 0, "factcheck must not be called when hard-check fires"
    assert len(openai_judge_calls) == 0, "_judge_openai must not be called when hard-check fires"


def test_run_qa_openai_pkg_missing_returns_one(tmp_path, monkeypatch):
    """provider='openai' with key set but openai pkg unavailable → returns 1, no judge calls."""
    import bench._retrieval as _r
    import bench.grounding as _g
    import bench.longmemeval as _lme

    monkeypatch.setenv("OPENAI_API_KEY", "fake-key")
    monkeypatch.setattr(qa, "_openai_available", lambda: False)

    factcheck_calls: list[bool] = []
    openai_judge_calls: list[bool] = []
    monkeypatch.setattr(_g, "_factcheck", lambda a, gt, m: factcheck_calls.append(True) or True)
    monkeypatch.setattr(
        qa, "_judge_openai", lambda q, gold, ans, model: openai_judge_calls.append(True) or True
    )
    monkeypatch.setattr(_lme, "_build_docs", lambda inst: [("s", "text")])
    monkeypatch.setattr(_r, "bm25_rank", lambda docs, q, k: ["s"])
    monkeypatch.setattr(_g, "_answer", lambda prefix, question, model, **kw: "ans")

    instances = _make_instances(n_single=1, n_multi=0)
    args = _make_args(tmp_path, backend="bm25", arms="retrieval", judge_provider="openai")

    rc = qa._run_qa(args, instances)

    assert rc == 1, f"expected rc=1 (pkg hard-check), got {rc}"
    assert len(factcheck_calls) == 0, "factcheck must not be called when hard-check fires"
    assert len(openai_judge_calls) == 0, "_judge_openai must not be called when hard-check fires"


# ─────────────────────────────────────────────────────────────────────────────
# NEW: seeded sampling tests
# ─────────────────────────────────────────────────────────────────────────────


def test_run_qa_sampling_reproducible(tmp_path, monkeypatch):
    """--sample N --seed S produces the same subset across two runs; seed change differs."""
    import bench._retrieval as _r
    import bench.grounding as _g
    import bench.longmemeval as _lme

    instances = _make_instances(n_single=5, n_multi=5)
    fixed_docs = [("s", "text")]

    monkeypatch.setattr(_r, "bm25_rank", lambda docs, q, k: ["s"])
    monkeypatch.setattr(_g, "_answer", lambda prefix, question, model, **kw: "ans")

    # --- Run 1: seed=0, sample=4 ---
    scored_ids_run1: list[str] = []

    def build_docs_spy_1(instance):
        scored_ids_run1.append(instance["question_id"])
        return fixed_docs

    out1 = tmp_path / "out1.json"
    monkeypatch.setattr(_lme, "_build_docs", build_docs_spy_1)
    monkeypatch.setattr(_g, "_factcheck", lambda a, gt, m: True)
    args1 = _make_args(tmp_path, backend="bm25", arms="retrieval", sample=4, seed=0)
    args1.out = out1
    qa._run_qa(args1, instances)

    # --- Run 2: same seed=0, sample=4 → must yield identical subset ---
    scored_ids_run2: list[str] = []

    def build_docs_spy_2(instance):
        scored_ids_run2.append(instance["question_id"])
        return fixed_docs

    out2 = tmp_path / "out2.json"
    monkeypatch.setattr(_lme, "_build_docs", build_docs_spy_2)
    monkeypatch.setattr(_g, "_factcheck", lambda a, gt, m: True)
    args2 = _make_args(tmp_path, backend="bm25", arms="retrieval", sample=4, seed=0)
    args2.out = out2
    qa._run_qa(args2, instances)

    # _build_docs is called twice per instance in the retrieval arm (once for ranking,
    # once inside _answer_one for context).  Deduplicate to get the unique scored set.
    unique_ids_run1 = sorted(set(scored_ids_run1))
    unique_ids_run2 = sorted(set(scored_ids_run2))
    assert len(unique_ids_run1) == 4, f"expected 4 unique instances, got {unique_ids_run1}"
    assert unique_ids_run1 == unique_ids_run2, "same seed must yield the same subset"

    # --- Run 3: seed=1 → different subset (deterministic: seed0=[6,9,0,2], seed1=[2,1,4,0]) ---
    scored_ids_seed1: list[str] = []

    def build_docs_spy_3(instance):
        scored_ids_seed1.append(instance["question_id"])
        return fixed_docs

    out3 = tmp_path / "out3.json"
    monkeypatch.setattr(_lme, "_build_docs", build_docs_spy_3)
    monkeypatch.setattr(_g, "_factcheck", lambda a, gt, m: True)
    args3 = _make_args(tmp_path, backend="bm25", arms="retrieval", sample=4, seed=1)
    args3.out = out3
    qa._run_qa(args3, instances)

    unique_ids_seed1 = sorted(set(scored_ids_seed1))
    assert unique_ids_seed1 != unique_ids_run1, "different seeds should yield different subsets"


def test_run_qa_sample_spans_multiple_types(tmp_path, monkeypatch):
    """sample=4 seed=0 over 5 single + 5 multi → question_type_distribution has >1 key."""
    import bench._retrieval as _r
    import bench.grounding as _g
    import bench.longmemeval as _lme

    # seed=0, sample=4 from 10 → indices [6,9,0,2] → 2 multi_session + 2 single_session
    instances = _make_instances(n_single=5, n_multi=5)
    args = _make_args(tmp_path, backend="bm25", arms="retrieval", sample=4, seed=0)

    monkeypatch.setattr(_lme, "_build_docs", lambda inst: [("s", "text")])
    monkeypatch.setattr(_r, "bm25_rank", lambda docs, q, k: ["s"])
    monkeypatch.setattr(_g, "_answer", lambda prefix, question, model, **kw: "ans")
    monkeypatch.setattr(_g, "_factcheck", lambda a, gt, m: True)

    qa._run_qa(args, instances)

    result = json.loads(args.out.read_text())
    dist = result["question_type_distribution"]
    assert len(dist) > 1, f"expected >1 question type in distribution, got: {dist}"


def test_run_qa_records_new_json_fields(tmp_path, monkeypatch):
    """Output JSON contains judge_provider, sample, seed, question_type_distribution."""
    import bench._retrieval as _r
    import bench.grounding as _g
    import bench.longmemeval as _lme

    instances = _make_instances(n_single=2, n_multi=1)
    args = _make_args(
        tmp_path,
        backend="bm25",
        arms="retrieval",
        judge_provider="claude",
        sample=2,
        seed=42,
    )

    monkeypatch.setattr(_lme, "_build_docs", lambda inst: [("s", "text")])
    monkeypatch.setattr(_r, "bm25_rank", lambda docs, q, k: ["s"])
    monkeypatch.setattr(_g, "_answer", lambda prefix, question, model, **kw: "ans")
    monkeypatch.setattr(_g, "_factcheck", lambda a, gt, m: True)

    qa._run_qa(args, instances)

    result = json.loads(args.out.read_text())
    assert "judge_provider" in result, "missing judge_provider key"
    assert "sample" in result, "missing sample key"
    assert "seed" in result, "missing seed key"
    assert "question_type_distribution" in result, "missing question_type_distribution key"
    assert result["judge_provider"] == "claude"
    assert result["sample"] == 2
    assert result["seed"] == 42


# ─────────────────────────────────────────────────────────────────────────────
# NEW: tuned reader instruction, openai reader path, auto-upgrade, canary
# ─────────────────────────────────────────────────────────────────────────────


def test_answer_one_claude_passes_tuned_instruction(monkeypatch):
    """Claude reader receives the LME-tuned instruction with question_date via instruction= kwarg.

    The new _answer_one(provider="claude") must pass instruction=<tuned> to _g._answer so
    the model sees prior-session framing + question_date instead of the generic default.
    """
    import bench.grounding as _g
    import bench.longmemeval as _lme

    captured: dict = {}

    def fake_answer(prefix, question, model, **kw):
        captured.update(kw)
        return "the answer"

    monkeypatch.setattr(_g, "_answer", fake_answer)
    monkeypatch.setattr(_lme, "_build_docs", lambda inst: [("sess-0", "session text")])

    instance = {
        "question": "What did we discuss?",
        "answer": "Something",
        "question_date": "2024-01-01",
        "haystack_session_ids": ["sess-0"],
        "haystack_sessions": [[{"role": "user", "content": "hello"}]],
        "answer_session_ids": ["sess-0"],
    }

    result = qa._answer_one(instance, ["sess-0"], "sonnet", 48000, provider="claude")

    assert result == "the answer"
    assert "instruction" in captured, "instruction= kwarg must be passed to _g._answer"
    instr = captured["instruction"]
    assert "2024-01-01" in instr, f"instruction must contain question_date, got: {instr!r}"
    for phrase in ("prior", "session", "only"):
        assert phrase in instr.lower(), f"instruction must contain {phrase!r}, got: {instr!r}"


def test_answer_one_openai_routes_to_openai_chat(monkeypatch):
    """provider='openai' routes _answer_one through _openai_chat, never through _g._answer."""
    import bench.grounding as _g
    import bench.longmemeval as _lme

    openai_calls: list[tuple] = []
    answer_calls: list = []

    def fake_openai_chat(model, system, user):
        openai_calls.append((model, system, user))
        return "the openai answer"

    monkeypatch.setattr(qa, "_openai_chat", fake_openai_chat)
    monkeypatch.setattr(
        _g, "_answer", lambda prefix, question, model, **kw: answer_calls.append(True) or ""
    )
    monkeypatch.setattr(_lme, "_build_docs", lambda inst: [("sess-0", "session text")])

    instance = {
        "question": "What did we discuss?",
        "answer": "Something",
        "question_date": "2024-01-01",
        "haystack_session_ids": ["sess-0"],
        "haystack_sessions": [[{"role": "user", "content": "hello"}]],
        "answer_session_ids": ["sess-0"],
    }

    result = qa._answer_one(instance, ["sess-0"], "gpt-4-turbo", 48000, provider="openai")

    assert result == "the openai answer", f"expected 'the openai answer', got {result!r}"
    assert len(openai_calls) == 1, f"_openai_chat must be called once, got {len(openai_calls)}"
    assert len(answer_calls) == 0, "_g._answer must NOT be called for openai provider"
    _, _, user_str = openai_calls[0]
    assert "What did we discuss?" in user_str, (
        f"user string must contain question text, got: {user_str!r}"
    )


def test_answer_one_openai_none_returns_empty(monkeypatch):
    """_openai_chat returning None for openai provider -> _answer_one returns ''."""
    import bench.longmemeval as _lme

    monkeypatch.setattr(qa, "_openai_chat", lambda model, system, user: None)
    monkeypatch.setattr(_lme, "_build_docs", lambda inst: [("sess-0", "text")])

    instance = {
        "question": "Q?",
        "answer": "A",
        "question_date": "2024-01-01",
        "haystack_session_ids": ["sess-0"],
        "haystack_sessions": [[{"role": "user", "content": "x"}]],
        "answer_session_ids": ["sess-0"],
    }

    result = qa._answer_one(instance, ["sess-0"], "gpt-4-turbo", 48000, provider="openai")
    assert result == "", f"expected '' on None from _openai_chat, got {result!r}"


def test_answer_one_openai_auto_upgrade(tmp_path, monkeypatch):
    """reader_provider=openai + reader_model=sonnet auto-upgrades to gpt-4-turbo in _run_qa.

    The auto-upgrade mirrors the judge pattern: resolved in _run_qa, threaded into the
    canary probe AND the per-instance _answer_one call.
    """
    import bench._retrieval as _r
    import bench.grounding as _g
    import bench.longmemeval as _lme

    recorded_models: list[str] = []

    def fake_openai_chat(model, system, user):
        recorded_models.append(model)
        return "ok"

    monkeypatch.setattr(qa, "_openai_available", lambda: True)
    monkeypatch.setenv("OPENAI_API_KEY", "fake-key")
    monkeypatch.setattr(qa, "_openai_chat", fake_openai_chat)
    monkeypatch.setattr(_lme, "_build_docs", lambda inst: [("s", "session text")])
    monkeypatch.setattr(_r, "bm25_rank", lambda docs, q, k: ["s"])
    monkeypatch.setattr(_g, "_factcheck", lambda a, gt, m: True)

    instances = _make_instances(n_single=1, n_multi=0)
    args = _make_args(
        tmp_path,
        backend="bm25",
        arms="retrieval",
        reader_provider="openai",
        reader_model="sonnet",
        judge_provider="claude",
    )

    qa._run_qa(args, instances)

    assert "gpt-4-turbo" in recorded_models, (
        f"expected gpt-4-turbo in models passed to _openai_chat, got: {recorded_models}"
    )


def test_run_qa_canary_none_returns_one(tmp_path, monkeypatch, capsys):
    """judge_provider=openai + _openai_chat->None (403) -> canary hard-stops, rc=1, no scoring."""
    import bench.grounding as _g
    import bench.longmemeval as _lme

    answer_calls: list = []
    factcheck_calls: list = []

    original_answer_one = qa._answer_one

    def spy_answer_one(instance, ids, reader_model, char_budget, **kw):
        answer_calls.append(True)
        return original_answer_one(instance, ids, reader_model, char_budget, **kw)

    monkeypatch.setattr(qa, "_answer_one", spy_answer_one)
    monkeypatch.setattr(_g, "_factcheck", lambda a, gt, m: factcheck_calls.append(True) or True)
    monkeypatch.setattr(qa, "_openai_available", lambda: True)
    monkeypatch.setenv("OPENAI_API_KEY", "fake-key")
    monkeypatch.setattr(qa, "_openai_chat", lambda model, system, user: None)
    monkeypatch.setattr(_lme, "_build_docs", lambda inst: [("s", "text")])

    instances = _make_instances(n_single=1, n_multi=0)
    args = _make_args(tmp_path, backend="bm25", arms="retrieval", judge_provider="openai")

    rc = qa._run_qa(args, instances)

    assert rc == 1, f"expected rc=1 from canary failure, got {rc}"
    assert len(answer_calls) == 0, f"_answer_one must not run; got {len(answer_calls)} calls"
    assert len(factcheck_calls) == 0, f"_factcheck must not run; got {len(factcheck_calls)} calls"
    captured = capsys.readouterr()
    assert "canary" in captured.out.lower(), (
        f"expected 'canary' in stdout for clear failure message, got: {captured.out!r}"
    )


def test_run_qa_canary_ok_proceeds(tmp_path, monkeypatch):
    """judge_provider=openai + canary passes ('ok') -> scoring loop runs normally."""
    import bench._retrieval as _r
    import bench.longmemeval as _lme

    answer_calls: list = []
    judge_calls: list = []

    def spy_answer_one(instance, ids, reader_model, char_budget, **kw):
        answer_calls.append((reader_model,))
        return "the answer"

    monkeypatch.setattr(qa, "_answer_one", spy_answer_one)
    monkeypatch.setattr(qa, "_openai_available", lambda: True)
    monkeypatch.setenv("OPENAI_API_KEY", "fake-key")
    monkeypatch.setattr(qa, "_openai_chat", lambda model, system, user: "ok")
    monkeypatch.setattr(
        qa, "_judge_openai", lambda q, gold, ans, model: judge_calls.append(True) or True
    )
    monkeypatch.setattr(_lme, "_build_docs", lambda inst: [("s", "text")])
    monkeypatch.setattr(_r, "bm25_rank", lambda docs, q, k: ["s"])

    instances = _make_instances(n_single=1, n_multi=0)
    args = _make_args(tmp_path, backend="bm25", arms="retrieval", judge_provider="openai")

    rc = qa._run_qa(args, instances)

    assert isinstance(rc, int), f"rc must be int, got {rc!r}"
    assert len(answer_calls) >= 1, "scoring must run: _answer_one was not called"
    assert len(judge_calls) >= 1, "scoring must run: _judge_openai was not called"
    assert args.out.exists(), "output JSON must be written when scoring runs"


def test_run_qa_records_reader_provider_json(tmp_path, monkeypatch):
    """Output JSON must contain 'reader_provider' key matching args.reader_provider."""
    import bench._retrieval as _r
    import bench.grounding as _g
    import bench.longmemeval as _lme

    monkeypatch.setattr(_lme, "_build_docs", lambda inst: [("s", "text")])
    monkeypatch.setattr(_r, "bm25_rank", lambda docs, q, k: ["s"])
    monkeypatch.setattr(_g, "_answer", lambda prefix, question, model, **kw: "ans")
    monkeypatch.setattr(_g, "_factcheck", lambda a, gt, m: True)

    instances = _make_instances(n_single=1, n_multi=0)
    args = _make_args(tmp_path, backend="bm25", arms="retrieval", reader_provider="claude")

    qa._run_qa(args, instances)

    result = json.loads(args.out.read_text())
    assert "reader_provider" in result, (
        f"missing reader_provider in output JSON; keys={list(result)}"
    )
    assert result["reader_provider"] == "claude"
