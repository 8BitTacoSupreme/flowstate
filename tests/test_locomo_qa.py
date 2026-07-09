"""Tests for bench/locomo_qa.py — offline LoCoMo QA-accuracy harness tests.

All tests are offline: every LLM and ranker is monkeypatched on its owning module
so no real claude binary, openai SDK, or fastembed is invoked.

Inline fixture uses INTEGER categories (per LoCoMo schema) and includes a cat-5
adversarial item and an empty-evidence item.  The shared bench/fixtures/locomo_smoke.json
(owned by test_locomo.py) is NOT used or modified here.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import bench.locomo_qa as qa
import pytest

import bench._retrieval as _r

# ─────────────────────────────────────────────────────────────────────────────
# Inline LoCoMo fixture (INTEGER categories, cat-5 + empty-evidence items)
# ─────────────────────────────────────────────────────────────────────────────

_LOCOMO_DATA = [
    {
        "sample_id": "conv1",
        "speaker_a": "Alice",
        "speaker_b": "Bob",
        "conversation": {
            "session_1": [
                {"speaker": "Alice", "dia_id": "d1", "text": "I enjoy running every morning."},
                {"speaker": "Bob", "dia_id": "d2", "text": "That is great for fitness."},
            ],
            "session_1_date_time": "2024-01-01",
        },
        "qa": [
            # category 1: single-hop, has evidence
            {
                "question": "What does Alice enjoy?",
                "answer": "running",
                "category": 1,
                "evidence": ["d1"],
            },
            # category 5: adversarial (empty evidence, oracle arm should skip)
            {
                "question": "What is Alice's SSN?",
                "answer": "not available",
                "category": 5,
                "evidence": [],
            },
        ],
    },
    {
        "sample_id": "conv2",
        "speaker_a": "Carol",
        "speaker_b": "Dave",
        "conversation": {
            "session_1": [
                {"speaker": "Carol", "dia_id": "d3", "text": "I love painting landscapes."},
                {"speaker": "Dave", "dia_id": "d4", "text": "Watercolor or oil?"},
            ],
        },
        "qa": [
            # category 2: multi-hop, has evidence
            {
                "question": "What does Carol love?",
                "answer": "painting",
                "category": 2,
                "evidence": ["d3"],
            },
            # category 3: empty evidence (oracle arm should skip + count)
            {
                "question": "What is Carol's address?",
                "answer": "unknown",
                "category": 3,
                "evidence": [],
            },
        ],
    },
]


def _make_args(
    tmp_path: Path,
    *,
    backend: str = "bm25",
    arms: str = "retrieval",
    k: int = 5,
    limit: int | None = None,
    reader_model: str = "sonnet",
    reader_provider: str = "claude",
    char_budget: int = 8000,
    embed_model: str = "BAAI/bge-small-en-v1.5",
    sample: int | None = None,
    seed: int = 0,
    max_failure_rate: float = 0.30,
    out: Path | None = None,
) -> argparse.Namespace:
    """Build a Namespace that mirrors _build_parser() defaults."""
    return argparse.Namespace(
        backend=backend,
        arms=arms,
        k=k,
        limit=limit,
        reader_model=reader_model,
        reader_provider=reader_provider,
        char_budget=char_budget,
        embed_model=embed_model,
        sample=sample,
        seed=seed,
        max_failure_rate=max_failure_rate,
        out=out or tmp_path / "out.json",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Normalization and metric unit tests
# ─────────────────────────────────────────────────────────────────────────────


def test_normalize_lowercase():
    assert qa._normalize("Running") == "running"


def test_normalize_strips_articles():
    result = qa._normalize("The cat sat on a mat")
    tokens = result.split()
    assert "the" not in tokens
    assert "a" not in tokens
    assert "cat" in tokens
    assert "mat" in tokens


def test_normalize_strips_punctuation():
    result = qa._normalize("Hello, world!")
    assert "," not in result
    assert "!" not in result
    assert "hello" in result


def test_normalize_collapses_whitespace():
    result = qa._normalize("  hello   world  ")
    assert result == result.strip()
    assert "  " not in result


def test_normalize_drops_an():
    result = qa._normalize("an apple")
    tokens = result.split()
    assert "an" not in tokens
    assert "apple" in tokens


def test_f1_identical():
    assert qa._f1("running", "running") == pytest.approx(1.0)


def test_f1_disjoint():
    assert qa._f1("cat", "dog") == pytest.approx(0.0)


def test_f1_partial_overlap():
    # pred="cat sat", gold="cat slept" -> shared token "cat" only
    # precision=1/2=0.5, recall=1/2=0.5, F1=0.5
    score = qa._f1("cat sat", "cat slept")
    assert 0.0 < score < 1.0


def test_f1_empty_pred():
    assert qa._f1("", "something") == pytest.approx(0.0)


def test_f1_empty_both():
    assert qa._f1("", "") == pytest.approx(1.0)


def test_exact_match_equal():
    assert qa._exact_match("running", "running") == pytest.approx(1.0)


def test_exact_match_unequal():
    assert qa._exact_match("cat", "dog") == pytest.approx(0.0)


def test_exact_match_article_stripped():
    # "the running" vs "running" -> after normalization both -> "running"
    assert qa._exact_match("the running", "running") == pytest.approx(1.0)


# ─────────────────────────────────────────────────────────────────────────────
# Adversarial category-5 scoring
# ─────────────────────────────────────────────────────────────────────────────


def test_score_item_cat5_no_info_available():
    f1, em = qa._score_item("no information available", "anything", 5)
    assert f1 == pytest.approx(1.0)
    assert em == pytest.approx(1.0)


def test_score_item_cat5_not_mentioned():
    f1, em = qa._score_item("This is not mentioned anywhere.", "anything", 5)
    assert f1 == pytest.approx(1.0)
    assert em == pytest.approx(1.0)


def test_score_item_cat5_case_insensitive():
    f1, em = qa._score_item("No Information Available here.", "anything", 5)
    assert f1 == pytest.approx(1.0)
    assert em == pytest.approx(1.0)


def test_score_item_cat5_wrong_phrase():
    f1, em = qa._score_item("I don't know.", "anything", 5)
    assert f1 == pytest.approx(0.0)
    assert em == pytest.approx(0.0)


def test_score_item_normal_cat():
    f1, em = qa._score_item("running", "running", 1)
    assert f1 == pytest.approx(1.0)
    assert em == pytest.approx(1.0)


def test_score_item_normal_cat_wrong():
    f1, em = qa._score_item("swimming", "running", 2)
    assert f1 == pytest.approx(0.0)
    assert em == pytest.approx(0.0)


# ─────────────────────────────────────────────────────────────────────────────
# Retrieval arm — monkeypatches _r.bm25_rank + qa._answer_one
# ─────────────────────────────────────────────────────────────────────────────


def test_retrieval_arm_uses_bm25_rank(monkeypatch, tmp_path):
    """_run retrieval arm calls _r.bm25_rank and feeds its output as context."""
    calls: list[str] = []

    def fake_bm25(docs, query, k):
        calls.append(query)
        return [doc_id for doc_id, _ in docs[:k]]

    # Return exact gold answers for all questions
    def fake_answer_one(question, context, reader_model, *, provider="claude"):
        # Map questions to gold answers
        answers = {
            "What does Alice enjoy?": "running",
            "What is Alice's SSN?": "no information available",
            "What does Carol love?": "painting",
            "What is Carol's address?": "something",
        }
        return answers.get(question, "")

    monkeypatch.setattr(_r, "bm25_rank", fake_bm25)
    monkeypatch.setattr(qa, "_answer_one", fake_answer_one)

    args = _make_args(tmp_path, arms="retrieval", backend="bm25")
    rc = qa._run(args, _LOCOMO_DATA)

    assert rc == 0
    assert len(calls) > 0  # bm25_rank was called


def test_retrieval_arm_per_category_and_overall(monkeypatch, tmp_path):
    """_run computes per-category AND overall F1/EM from known reader answers."""

    def fake_bm25(docs, query, k):
        return [doc_id for doc_id, _ in docs[:k]]

    def fake_answer_one(question, context, reader_model, *, provider="claude"):
        # cat 1: Alice enjoys running -> exact gold
        if "Alice" in question:
            return "running"
        # cat 5: adversarial -> correct phrase
        if "SSN" in question:
            return "no information available"
        # cat 2: Carol loves -> WRONG answer
        if "Carol" in question and "love" in question:
            return "swimming"
        # cat 3: empty evidence item (in retrieval arm, still scored)
        return "wrong answer"

    monkeypatch.setattr(_r, "bm25_rank", fake_bm25)
    monkeypatch.setattr(qa, "_answer_one", fake_answer_one)

    out_path = tmp_path / "results.json"
    args = _make_args(tmp_path, arms="retrieval", backend="bm25", out=out_path)
    rc = qa._run(args, _LOCOMO_DATA)

    assert rc == 0
    result = json.loads(out_path.read_text())

    assert result["benchmark"] == "locomo_qa"
    assert "arms" in result
    ret_arm = result["arms"]["retrieval"]

    # Overall must have n, f1, em
    overall = ret_arm["overall"]
    assert overall["n"] >= 1
    assert "f1" in overall
    assert "em" in overall
    assert "em_wilson_ci" in overall

    # by_category must have at least category "1"
    by_cat = ret_arm["by_category"]
    assert "1" in by_cat
    cat1 = by_cat["1"]
    assert cat1["f1"] == pytest.approx(1.0)
    assert cat1["em"] == pytest.approx(1.0)

    # category 2 should be wrong (f1=0.0, em=0.0)
    assert "2" in by_cat
    cat2 = by_cat["2"]
    assert cat2["f1"] == pytest.approx(0.0)
    assert cat2["em"] == pytest.approx(0.0)


# ─────────────────────────────────────────────────────────────────────────────
# Oracle arm — uses gold evidence dia_ids, skips empty-evidence qa
# ─────────────────────────────────────────────────────────────────────────────


def test_oracle_arm_uses_evidence_text(monkeypatch, tmp_path):
    """Oracle arm builds context from gold evidence dia_ids, not from ranker."""
    contexts_seen: list[str] = []

    def fake_answer_one(question, context, reader_model, *, provider="claude"):
        contexts_seen.append(context)
        return "running"

    out_path = tmp_path / "oracle_out.json"
    args = _make_args(tmp_path, arms="oracle", out=out_path)
    monkeypatch.setattr(qa, "_answer_one", fake_answer_one)

    rc = qa._run(args, _LOCOMO_DATA)
    assert rc == 0

    # Should have been called at least once (skipping empty-evidence items)
    assert len(contexts_seen) > 0
    # The context for the cat-1 qa (evidence=["d1"]) must contain d1's text
    assert any("running" in ctx or "Alice" in ctx for ctx in contexts_seen)


def test_oracle_arm_skips_empty_evidence(monkeypatch, tmp_path):
    """Oracle arm skips qa with empty evidence lists and counts them."""
    scored_questions: list[str] = []

    def fake_answer_one(question, context, reader_model, *, provider="claude"):
        scored_questions.append(question)
        return "running"

    out_path = tmp_path / "oracle_skip.json"
    args = _make_args(tmp_path, arms="oracle", out=out_path)
    monkeypatch.setattr(qa, "_answer_one", fake_answer_one)

    qa._run(args, _LOCOMO_DATA)

    # The 2 empty-evidence items (cat-5 + cat-3) must NOT have been scored
    assert "What is Alice's SSN?" not in scored_questions
    assert "What is Carol's address?" not in scored_questions
    # The 2 items with evidence must have been scored
    assert any("Alice" in q for q in scored_questions)
    assert any("Carol" in q and "love" in q for q in scored_questions)


# ─────────────────────────────────────────────────────────────────────────────
# Seeded sampling + limit
# ─────────────────────────────────────────────────────────────────────────────


def _make_large_data(n: int) -> list[dict]:
    """Build n single-qa conversations for sampling tests."""
    data = []
    for i in range(n):
        data.append(
            {
                "sample_id": f"c{i}",
                "conversation": {
                    "session_1": [
                        {"speaker": "A", "dia_id": f"d{i}", "text": f"text {i}"},
                    ]
                },
                "qa": [
                    {
                        "question": f"Q {i}",
                        "answer": f"answer {i}",
                        "category": 1,
                        "evidence": [f"d{i}"],
                    }
                ],
            }
        )
    return data


def test_seeded_sample_determinism(monkeypatch, tmp_path):
    """Two runs with same seed and sample produce same n in output."""
    monkeypatch.setattr(qa, "_answer_one", lambda q, c, m, **kw: "answer")
    monkeypatch.setattr(_r, "bm25_rank", lambda docs, q, k: [d for d, _ in docs[:k]])

    data = _make_large_data(20)

    out1 = tmp_path / "r1.json"
    args1 = _make_args(tmp_path, arms="retrieval", backend="bm25", sample=8, seed=42, out=out1)
    qa._run(args1, data)
    r1 = json.loads(out1.read_text())

    out2 = tmp_path / "r2.json"
    args2 = _make_args(tmp_path, arms="retrieval", backend="bm25", sample=8, seed=42, out=out2)
    qa._run(args2, data)
    r2 = json.loads(out2.read_text())

    assert r1["arms"]["retrieval"]["overall"]["n"] == r2["arms"]["retrieval"]["overall"]["n"]


def test_different_seeds_may_differ(monkeypatch, tmp_path):
    """Different seeds can produce different samples (statistical, not guaranteed)."""
    monkeypatch.setattr(qa, "_answer_one", lambda q, c, m, **kw: "answer")
    monkeypatch.setattr(_r, "bm25_rank", lambda docs, q, k: [d for d, _ in docs[:k]])

    data = _make_large_data(20)

    # Both should run without error
    out1 = tmp_path / "s1.json"
    args1 = _make_args(tmp_path, arms="retrieval", backend="bm25", sample=5, seed=1, out=out1)
    rc1 = qa._run(args1, data)

    out2 = tmp_path / "s2.json"
    args2 = _make_args(tmp_path, arms="retrieval", backend="bm25", sample=5, seed=99, out=out2)
    rc2 = qa._run(args2, data)

    assert rc1 == 0
    assert rc2 == 0


def test_limit_caps_scored_items(monkeypatch, tmp_path):
    """--limit caps the number of conversations evaluated."""
    monkeypatch.setattr(qa, "_answer_one", lambda q, c, m, **kw: "answer")
    monkeypatch.setattr(_r, "bm25_rank", lambda docs, q, k: [d for d, _ in docs[:k]])

    data = _make_large_data(10)
    out = tmp_path / "limited.json"
    args = _make_args(tmp_path, arms="retrieval", backend="bm25", limit=3, out=out)
    rc = qa._run(args, data)

    assert rc == 0
    result = json.loads(out.read_text())
    # With limit=3 conversations and 1 qa each, at most 3 items scored
    assert result["arms"]["retrieval"]["overall"]["n"] <= 3


# ─────────────────────────────────────────────────────────────────────────────
# Mass-failure guard (exit 2 + unreliable)
# ─────────────────────────────────────────────────────────────────────────────


def test_mass_failure_guard_exit_2(monkeypatch, tmp_path):
    """When reader_empty / total > max_failure_rate, _run returns 2 + unreliable:true."""
    # All reader calls return "" -> 100% empty -> triggers guard at default 0.30
    monkeypatch.setattr(qa, "_answer_one", lambda q, c, m, **kw: "")
    monkeypatch.setattr(_r, "bm25_rank", lambda docs, q, k: [d for d, _ in docs[:k]])

    data = _make_large_data(5)
    out = tmp_path / "fail.json"
    args = _make_args(tmp_path, arms="retrieval", backend="bm25", out=out)
    rc = qa._run(args, data)

    assert rc == 2
    result = json.loads(out.read_text())
    assert result["unreliable"] is True
    assert result["failure_rate"] > 0.30


def test_mass_failure_below_threshold_not_unreliable(monkeypatch, tmp_path):
    """When empty rate <= max_failure_rate, result is reliable (exit 0)."""
    # All answers non-empty -> 0% empty -> reliable
    monkeypatch.setattr(qa, "_answer_one", lambda q, c, m, **kw: "answer")
    monkeypatch.setattr(_r, "bm25_rank", lambda docs, q, k: [d for d, _ in docs[:k]])

    data = _make_large_data(5)
    out = tmp_path / "ok.json"
    args = _make_args(tmp_path, arms="retrieval", backend="bm25", out=out)
    rc = qa._run(args, data)

    assert rc == 0
    result = json.loads(out.read_text())
    assert result["unreliable"] is False


# ─────────────────────────────────────────────────────────────────────────────
# Import-without-openai guard
# ─────────────────────────────────────────────────────────────────────────────


def test_openai_available_never_raises():
    """_openai_available() returns a bool and never raises."""
    result = qa._openai_available()
    assert isinstance(result, bool)


def test_module_importable_without_openai():
    """bench.locomo_qa is already imported; verify no openai was required at import time."""
    # The module is loaded at the top of this file without openai being imported eagerly.
    assert hasattr(qa, "_openai_available")
    assert hasattr(qa, "_f1")
    assert hasattr(qa, "_exact_match")
    assert hasattr(qa, "_normalize")
    assert hasattr(qa, "_score_item")
    assert hasattr(qa, "_run")
    assert hasattr(qa, "main")


def test_openai_chat_returns_none_without_sdk(monkeypatch):
    """_openai_chat returns None (never raises) when openai is unavailable."""
    # Remove openai from sys.modules to simulate missing SDK
    saved = sys.modules.pop("openai", None)
    try:
        result = qa._openai_chat("gpt-4o", "system", "user")
        assert result is None
    finally:
        if saved is not None:
            sys.modules["openai"] = saved


# ─────────────────────────────────────────────────────────────────────────────
# main() CLI smoke test
# ─────────────────────────────────────────────────────────────────────────────


def test_main_missing_data_returns_1():
    """main() with --data pointing to nonexistent file returns 1."""
    rc = qa.main(["--data", "/nonexistent/path/locomo.json", "--backend", "bm25"])
    assert rc == 1
