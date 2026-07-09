"""LoCoMo QA-accuracy harness.

Measures reader answer quality on the LoCoMo benchmark using OFFICIAL string-based
metrics (token-overlap F1 + exact-match + the category-5 adversarial rule).  No LLM
judge is used.

Complements bench/locomo.py (retrieval-coverage) with a downstream answer-accuracy
signal, mirroring the longmemeval_qa.py shape but replacing the judge with deterministic
string metrics.

ADD-ONLY: this module imports from bench.locomo, bench._retrieval, and bench.grounding
via module-attribute access so tests can monkeypatch any collaborator on its owning module.
Do NOT add from-imports for functions that callers need to patch.

Usage:
    python -m bench.locomo_qa \\
        --data <locomo_data.json> \\
        --backend bm25 \\
        --arms retrieval,oracle \\
        --k 5 \\
        --reader-provider claude \\
        --sample 200 --seed 0 \\
        --out <results.json>
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
from pathlib import Path

import bench._retrieval as _r
import bench.grounding as _g
import bench.locomo as _loc

# ─────────────────────────────────────────────────────────────────────────────
# LoCoMo-tuned reader instruction
# ─────────────────────────────────────────────────────────────────────────────

_READER_INSTRUCTION = (
    "Answer using ONLY information present in the conversation context above. "
    "Be specific and concise. "
    "If the context does not contain the answer, say 'no information available'."
)

# ─────────────────────────────────────────────────────────────────────────────
# Lazy OpenAI seam — copied verbatim from bench/longmemeval_qa.py
# ─────────────────────────────────────────────────────────────────────────────

# SDK-level retry/backoff constants for the OpenAI client.
# max_retries=10 with the SDK's built-in exponential + jitter backoff absorbs 429
# Retry-After headers common under Tier-1 (30k-TPM) limits.  timeout=120.0 allows
# long queued requests to complete rather than erroring with a connection timeout.
_OPENAI_MAX_RETRIES: int = 10
_OPENAI_TIMEOUT: float = 120.0


def _openai_available() -> bool:
    """Return True if the openai package can be imported; never raises."""
    try:
        import openai  # noqa: F401

        return True
    except ImportError:
        return False


def _openai_chat(model: str, system: str, user: str) -> str | None:
    """Call the OpenAI chat completions API lazily; never raises.

    Lazily imports openai (so the module loads without the SDK installed).
    Returns the first-choice message content string, or None on any error.

    Args:
        model: OpenAI model name (e.g. "gpt-4o").
        system: System prompt string.
        user: User message string.

    Returns:
        Response text string, or None on any failure.
    """
    try:
        import openai

        client = openai.OpenAI(max_retries=_OPENAI_MAX_RETRIES, timeout=_OPENAI_TIMEOUT)
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0,
            max_tokens=128,
        )
        return resp.choices[0].message.content
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Normalization and string metrics (LoCoMo official, NO judge)
# ─────────────────────────────────────────────────────────────────────────────

_ARTICLES: frozenset[str] = frozenset({"a", "an", "the"})
_PUNCT_RE = re.compile(r"[^\w\s]")
_WS_RE = re.compile(r"\s+")


def _normalize(s: str) -> str:
    """Lowercase, strip punctuation, drop articles a/an/the, collapse whitespace.

    This is LoCoMo's official normalization step applied before all string metrics.

    Args:
        s: Raw string to normalize.

    Returns:
        Normalized string.
    """
    s = s.lower()
    s = _PUNCT_RE.sub(" ", s)
    tokens = [t for t in s.split() if t not in _ARTICLES]
    return _WS_RE.sub(" ", " ".join(tokens)).strip()


def _stem(token: str) -> str:
    """Approximate suffix-stripping stemmer (no NLTK dependency).

    Approximates NLTK PorterStemmer by stripping common English suffixes in priority
    order.  Deliberately avoids any third-party NLP library so the module stays
    dependency-free.  Minimum token-length guards prevent over-stripping short words.

    Args:
        token: A single lowercase normalized token.

    Returns:
        Stemmed token string.
    """
    if len(token) > 6 and token.endswith("ation"):
        return token[:-5]
    if len(token) > 5 and token.endswith("ness"):
        return token[:-4]
    if len(token) > 5 and token.endswith("ing"):
        return token[:-3]
    if len(token) > 4 and token.endswith("ers"):
        return token[:-3]
    if len(token) > 4 and token.endswith("ed"):
        return token[:-2]
    if len(token) > 4 and token.endswith("er"):
        return token[:-2]
    if len(token) > 4 and token.endswith("es"):
        return token[:-2]
    if len(token) > 4 and token.endswith("ly"):
        return token[:-2]
    if len(token) > 3 and token.endswith("s"):
        return token[:-1]
    return token


def _tokenize(s: str) -> list[str]:
    """Normalize and stem a string, returning a token list."""
    return [_stem(t) for t in _normalize(s).split()]


def _f1(pred: str, gold: str) -> float:
    """Token-overlap F1 with normalization + light stem.  Both empty -> 1.0.

    Implements LoCoMo's official F1 metric: multiset precision and recall over
    normalized, stemmed tokens.

    Args:
        pred: Predicted answer string.
        gold: Gold answer string.

    Returns:
        F1 score in [0.0, 1.0].
    """
    pred_tokens = _tokenize(pred)
    gold_tokens = _tokenize(gold)

    if not pred_tokens and not gold_tokens:
        return 1.0
    if not pred_tokens or not gold_tokens:
        return 0.0

    # Multiset intersection
    pred_counts: dict[str, int] = {}
    for t in pred_tokens:
        pred_counts[t] = pred_counts.get(t, 0) + 1
    gold_counts: dict[str, int] = {}
    for t in gold_tokens:
        gold_counts[t] = gold_counts.get(t, 0) + 1

    common = sum(min(pred_counts.get(t, 0), gold_counts[t]) for t in gold_counts)

    if common == 0:
        return 0.0

    precision = common / len(pred_tokens)
    recall = common / len(gold_tokens)
    return 2 * precision * recall / (precision + recall)


def _exact_match(pred: str, gold: str) -> float:
    """Normalized token-SET equality.  Returns 1.0 or 0.0.

    Normalizes and stems both strings, then compares as token sets (not ordered
    sequences).  Articles and punctuation are stripped before comparison.

    Args:
        pred: Predicted answer string.
        gold: Gold answer string.

    Returns:
        1.0 if token sets match exactly, else 0.0.
    """
    return 1.0 if set(_tokenize(pred)) == set(_tokenize(gold)) else 0.0


# Adversarial phrases (category 5) — case-insensitive substring match.
_ADV_PHRASES: tuple[str, ...] = ("no information available", "not mentioned")


def _score_item(pred: str, gold: str, category: int) -> tuple[float, float]:
    """Score one QA item.  Returns (f1, em).

    Category-5 adversarial rule: score is 1.0 iff the prediction contains
    "no information available" OR "not mentioned" (case-insensitive substring).
    All other categories use the standard _f1 and _exact_match metrics.
    Adversarial hits contribute to both F1 and EM columns as their 0/1 score.

    Args:
        pred: Predicted answer string.
        gold: Gold answer string (ignored for category 5).
        category: Integer LoCoMo category (1-5).

    Returns:
        Tuple of (f1_score, exact_match_score) each in [0.0, 1.0].
    """
    if category == 5:
        pred_lower = pred.lower()
        hit = any(phrase in pred_lower for phrase in _ADV_PHRASES)
        score = 1.0 if hit else 0.0
        return score, score
    return _f1(pred, gold), _exact_match(pred, gold)


# ─────────────────────────────────────────────────────────────────────────────
# Reader helpers
# ─────────────────────────────────────────────────────────────────────────────


def _build_context(
    docs: list[tuple[str, str]],
    dia_ids: list[str],
    *,
    char_budget: int = 8000,
) -> str:
    """Build a reader context string from selected dia_ids.

    Looks up each dia_id in docs, joining their texts with double newlines in the
    order given by dia_ids.  Result is truncated to char_budget characters.  Returns
    "" when dia_ids is empty or all are absent from docs.  Never raises.

    Args:
        docs: List of (dia_id, text) pairs from _loc._build_docs.
        dia_ids: Ordered list of dia_ids to include.
        char_budget: Maximum character length of the returned context.

    Returns:
        Context string, truncated to char_budget chars.
    """
    try:
        id_to_text: dict[str, str] = {doc_id: text for doc_id, text in docs}
        texts = [id_to_text[did] for did in dia_ids if did in id_to_text]
        result = "\n\n".join(texts)
        return result[:char_budget]
    except Exception:
        return ""


def _answer_one(
    question: str,
    context: str,
    reader_model: str,
    *,
    provider: str = "claude",
) -> str:
    """Call the reader model with the given context and question.

    For provider=="claude": calls bench.grounding._answer.
    For provider=="openai": routes through _openai_chat.
    Returns "" on any failure.  Never raises.

    Args:
        question: The question to answer.
        context: Conversation context string (already char-budget truncated).
        reader_model: Model name for the reader call.
        provider: Reader provider — "claude" (default) or "openai".

    Returns:
        Answer string from the reader, or "" on failure.
    """
    try:
        if provider == "openai":
            system = (
                "You are a helpful assistant that answers questions "
                "from personal conversation context."
            )
            user = f"{context}\n\nQUESTION: {question}\n\n{_READER_INSTRUCTION}"
            return _openai_chat(reader_model, system, user) or ""
        return _g._answer(context, question, reader_model, instruction=_READER_INSTRUCTION)
    except Exception:
        return ""


# ─────────────────────────────────────────────────────────────────────────────
# Main evaluation loop
# ─────────────────────────────────────────────────────────────────────────────


def _run(args: argparse.Namespace, data: list[dict]) -> int:
    """Run the LoCoMo QA-accuracy evaluation over the given conversations.

    Evaluates one or more arms ("retrieval", "oracle") and aggregates accuracy
    per LoCoMo category (1-5) AND overall: mean_f1, mean_em, n, Wilson CI on the EM
    rate.  Tallies reader_empty and applies the mass-failure guard.

    The openai prereq hard-check + per-model canary probe fires when
    reader_provider=="openai" — this is the ONE deliberate hard-stop (returns 1).

    Never raises — outer try/except returns 1 on any unexpected failure.

    Args:
        args: Parsed argument namespace (see _build_parser for attribute list).
        data: List of LoCoMo conversation dicts.

    Returns:
        0 on success, 1 on hard error, 2 when mass-failure guard triggers.
    """
    try:
        reader_provider = args.reader_provider
        effective_reader_model = args.reader_model

        # Default openai reader model
        if reader_provider == "openai" and effective_reader_model == "sonnet":
            effective_reader_model = "gpt-4-turbo"

        # Hard-check: openai requires OPENAI_API_KEY and the openai package.
        if reader_provider == "openai" and not (
            os.environ.get("OPENAI_API_KEY") and _openai_available()
        ):
            print("--reader-provider openai requires OPENAI_API_KEY and `pip install -e .[eval]`")
            return 1

        # Upfront canary: one real probe before the scoring loop.
        if reader_provider == "openai":
            raw = _openai_chat(effective_reader_model, "ping", "Reply with the single word: ok")
            if raw is None:
                print(
                    f"openai canary failed for model '{effective_reader_model}' — check the "
                    f"key's project has access to that model; falling back is disabled to "
                    f"avoid silently scoring everything wrong"
                )
                return 1

        arms_requested = [a.strip() for a in args.arms.split(",") if a.strip()]

        # Sampling (sample first, then limit)
        processed = list(data)
        if args.sample is not None:
            processed = random.Random(args.seed).sample(processed, min(args.sample, len(processed)))
        if args.limit is not None:
            processed = processed[: args.limit]

        reader_empty_count = 0
        arm_data: dict[str, dict] = {}

        for arm_name in arms_requested:
            if arm_name not in {"retrieval", "oracle"}:
                continue

            # Per-arm category + overall accumulators
            per_cat_f1: dict[str, list[float]] = {}
            per_cat_em: dict[str, list[float]] = {}
            overall_f1_list: list[float] = []
            overall_em_list: list[float] = []
            oracle_skipped = 0

            # Resolve semantic backend ONCE before the conversation loop (Task A parity)
            embed_fn = None
            if arm_name == "retrieval" and args.backend == "semantic":
                embed_fn, available = _r.semantic_backend_available(args.embed_model)
                if not available:
                    print(
                        "note: semantic backend unavailable (fastembed/sqlite_vec missing); "
                        "skipping retrieval arm"
                    )
                    continue

            for conv in processed:
                try:
                    docs = _loc._build_docs(conv)

                    for qa_item in conv.get("qa", []):
                        try:
                            question = qa_item.get("question", "")
                            gold = qa_item.get("answer", "")
                            category = qa_item.get("category", 0)
                            evidence = qa_item.get("evidence", [])

                            if arm_name == "oracle":
                                # Oracle arm: skip QA items with empty evidence
                                if not evidence:
                                    oracle_skipped += 1
                                    continue
                                dia_ids = [str(e) for e in evidence]
                            else:
                                # Retrieval arm: rank docs to get dia_ids
                                if args.backend == "bm25":
                                    dia_ids = _r.bm25_rank(docs, question, args.k)
                                else:
                                    dia_ids = _r.semantic_rank(docs, question, args.k, embed_fn)

                            context = _build_context(docs, dia_ids, char_budget=args.char_budget)
                            answer = _answer_one(
                                question, context, effective_reader_model, provider=reader_provider
                            )

                            if answer == "":
                                reader_empty_count += 1

                            f1_score, em_score = _score_item(answer, gold, category)
                            cat_key = str(category)
                            per_cat_f1.setdefault(cat_key, []).append(f1_score)
                            per_cat_em.setdefault(cat_key, []).append(em_score)
                            overall_f1_list.append(f1_score)
                            overall_em_list.append(em_score)

                        except Exception:
                            continue
                except Exception:
                    continue

            # Build per-category stats blocks
            by_category: dict[str, dict] = {}
            for cat_key in per_cat_f1:
                f1_vals = per_cat_f1[cat_key]
                em_vals = per_cat_em[cat_key]
                n_cat = len(f1_vals)
                em_successes = sum(1 for v in em_vals if v >= 1.0)
                low, high = _g._wilson(em_successes, n_cat)
                by_category[cat_key] = {
                    "f1": round(sum(f1_vals) / n_cat, 4),
                    "em": round(sum(em_vals) / n_cat, 4),
                    "n": n_cat,
                    "em_wilson_ci": [round(low, 4), round(high, 4)],
                }

            # Build overall stats block
            overall_n = len(overall_f1_list)
            if overall_n > 0:
                mean_f1 = sum(overall_f1_list) / overall_n
                mean_em = sum(overall_em_list) / overall_n
                em_successes_total = sum(1 for v in overall_em_list if v >= 1.0)
                low_overall, high_overall = _g._wilson(em_successes_total, overall_n)
            else:
                mean_f1 = mean_em = 0.0
                low_overall = high_overall = 0.0

            arm_data[arm_name] = {
                "overall": {
                    "f1": round(mean_f1, 4),
                    "em": round(mean_em, 4),
                    "n": overall_n,
                    "em_wilson_ci": [round(low_overall, 4), round(high_overall, 4)],
                },
                "by_category": by_category,
                "oracle_skipped": oracle_skipped if arm_name == "oracle" else 0,
            }

        total_n = sum(arm_data[arm]["overall"]["n"] for arm in arm_data)
        failure_rate = reader_empty_count / max(1, total_n)
        unreliable = failure_rate > args.max_failure_rate

        output: dict = {
            "benchmark": "locomo_qa",
            "n": total_n,
            "sample": args.sample,
            "seed": args.seed,
            "backend": args.backend,
            "reader_provider": reader_provider,
            "reader_model": effective_reader_model,
            "arms": arm_data,
            "unreliable": unreliable,
            "failure_rate": round(failure_rate, 4),
            "reader_empty": reader_empty_count,
        }

        # Console summary table
        print(f"\n{'arm':<12} {'f1':>8} {'em':>8} {'em_ci':>22} {'n':>6}")
        print("-" * 62)
        for arm_name, arm_stats in arm_data.items():
            ov = arm_stats["overall"]
            ci = f"[{ov['em_wilson_ci'][0]:.3f}, {ov['em_wilson_ci'][1]:.3f}]"
            print(f"{arm_name:<12} {ov['f1']:>8.3f} {ov['em']:>8.3f} {ci:>22} {ov['n']:>6}")

        # Write JSON output
        if args.out is not None:
            try:
                Path(args.out).write_text(json.dumps(output, indent=2))
            except Exception as exc:
                print(f"warning: could not write results to {args.out}: {exc}")

        if unreliable:
            print(
                f"WARNING: {reader_empty_count}/{total_n} reader calls returned empty "
                f"(failure_rate={failure_rate:.1%} > threshold={args.max_failure_rate:.1%}). "
                f"Results are UNRELIABLE — check reader connectivity."
            )
            return 2

        return 0

    except Exception as exc:
        print(f"error: unexpected failure: {exc}")
        return 1


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="bench.locomo_qa",
        description="LoCoMo QA-accuracy benchmark (string metrics, no LLM judge).",
    )
    parser.add_argument("--data", type=Path, required=True, help="Path to LoCoMo JSON file.")
    parser.add_argument(
        "--backend",
        choices=["bm25", "semantic"],
        default="bm25",
        help="Retrieval backend for the retrieval arm (default: bm25).",
    )
    parser.add_argument(
        "--k",
        type=int,
        default=5,
        help="Number of retrieved turns to use as reader context (default: 5).",
    )
    parser.add_argument(
        "--arms",
        default="retrieval,oracle",
        help="Comma-separated arms to evaluate: retrieval, oracle (default: both).",
    )
    parser.add_argument(
        "--reader-provider",
        choices=["claude", "openai"],
        default="claude",
        dest="reader_provider",
        help="Reader provider (default: claude).",
    )
    parser.add_argument(
        "--reader-model",
        default="sonnet",
        dest="reader_model",
        help="Reader model name (default: sonnet for claude, gpt-4-turbo for openai).",
    )
    parser.add_argument(
        "--embed-model",
        default="BAAI/bge-small-en-v1.5",
        dest="embed_model",
        help="Embedding model for semantic backend.",
    )
    parser.add_argument(
        "--char-budget",
        type=int,
        default=8000,
        dest="char_budget",
        help="Maximum character budget for reader context (default: 8000).",
    )
    parser.add_argument(
        "--sample",
        type=int,
        default=None,
        help="Randomly sample N conversations before --limit (seeded by --seed).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=0,
        help="Random seed for --sample (default: 0).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Cap the number of conversations evaluated.",
    )
    parser.add_argument(
        "--max-failure-rate",
        type=float,
        default=0.30,
        dest="max_failure_rate",
        help=(
            "Fraction of reader calls that may be empty before results are flagged "
            "UNRELIABLE (exit 2, unreliable:true in JSON). Default: 0.30."
        ),
    )
    parser.add_argument("--out", type=Path, default=None, help="Output JSON path.")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the LoCoMo QA-accuracy benchmark.  Returns 0 on success, 1/2 on error."""
    args = _build_parser().parse_args(argv)
    data = _loc._load_data(args.data)
    if data is None:
        print(f"note: could not load data from {args.data}")
        return 1
    return _run(args, data)


if __name__ == "__main__":
    sys.exit(main())
