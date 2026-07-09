"""LongMemEval session-level Recall@k retrieval harness.

Compares FlowState's semantic backend (fastembed + sqlite-vec) against a BM25/FTS5
baseline on the LongMemEval benchmark (session-level Recall@k metric).

Metrics (per the LongMemEval eval spec):
    recalled = set(ranked_ids[:k])
    recall_any@k = 1.0 if any(g in recalled for g in gold) else 0.0
    recall_all@k = 1.0 if all(g in recalled for g in gold) else 0.0

Instances with empty answer_session_ids (abstentions) are skipped and counted.
Malformed instances (ragged/missing haystack fields) are skipped and counted.

ADD-ONLY: do NOT modify bench/grounding.py or anything under flowstate/.

Usage:
    python -m bench.longmemeval \\
        --data <lme_data.json> \\
        --backends bm25,semantic \\
        --k 5,10 \\
        --out <results.json>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import bench._retrieval as _retrieval
from bench.grounding import _wilson


def _load_data(path: Path | str) -> list[dict] | None:
    """Load a LongMemEval JSON file. Never raises.

    Returns a non-empty list of instance dicts on success, or None on any
    error (missing file, parse error, empty list, non-list result).
    """
    try:
        data = json.loads(Path(path).read_text())
        if not isinstance(data, list) or not data:
            return None
        return data
    except Exception:
        return None


def _build_docs(instance: dict) -> list[tuple[str, str]] | None:
    """Build (session_id, session_text) doc list for one LME instance.

    session_text joins turns as "{role}: {content}" lines.
    Returns None when haystack_session_ids/haystack_sessions are absent,
    non-list, or have mismatched lengths.  Never raises.
    """
    try:
        sids = instance.get("haystack_session_ids")
        sessions = instance.get("haystack_sessions")
        if not isinstance(sids, list) or not isinstance(sessions, list):
            return None
        if len(sids) != len(sessions):
            return None
        docs: list[tuple[str, str]] = []
        for sid, session in zip(sids, sessions, strict=False):
            if not isinstance(session, list):
                continue
            text = "\n".join(
                f"{t.get('role', '')}: {t.get('content', '')}"
                for t in session
                if isinstance(t, dict)
            )
            docs.append((str(sid), text))
        return docs if docs else None
    except Exception:
        return None


def _recall_any(ranked_ids: list[str], gold: list[str], k: int) -> float:
    """recall_any@k: 1.0 if any gold id is in ranked_ids[:k], else 0.0."""
    if not gold:
        return 0.0
    recalled = set(ranked_ids[:k])
    return 1.0 if any(g in recalled for g in gold) else 0.0


def _recall_all(ranked_ids: list[str], gold: list[str], k: int) -> float:
    """recall_all@k: 1.0 if all gold ids are in ranked_ids[:k], else 0.0."""
    if not gold:
        return 0.0
    recalled = set(ranked_ids[:k])
    return 1.0 if all(g in recalled for g in gold) else 0.0


def _aggregate(results: list[dict], ks: list[int]) -> dict:
    """Aggregate recall_all and recall_any metrics over evaluated instances.

    For each metric and each k, computes mean + Wilson CI (treating 1.0 scores
    as successes for the Wilson CI calculation).

    Args:
        results: List of dicts with keys 'ranked' and 'gold'.
        ks: List of k values to compute metrics for.

    Returns:
        Dict with 'recall_all' and 'recall_any' keys, each mapping k-string to stats.
    """
    agg: dict = {}
    for metric_name, metric_fn in (
        ("recall_all", _recall_all),
        ("recall_any", _recall_any),
    ):
        agg[metric_name] = {}
        for k in ks:
            scores = [metric_fn(r["ranked"], r["gold"], k) for r in results]
            n = len(scores)
            successes = sum(1 for s in scores if s == 1.0)
            mean = sum(scores) / n if n else 0.0
            low, high = _wilson(successes, n)
            agg[metric_name][str(k)] = {
                "mean": round(mean, 4),
                "n": n,
                "wilson_ci": [round(low, 4), round(high, 4)],
            }
    return agg


def main(argv: list[str] | None = None) -> int:
    """Run the LongMemEval retrieval benchmark. Returns 0 on success, 1 on error."""
    parser = argparse.ArgumentParser(
        prog="bench.longmemeval",
        description="LongMemEval session-level Recall@k retrieval benchmark.",
    )
    parser.add_argument("--data", type=Path, required=True, help="Path to LongMemEval JSON file.")
    parser.add_argument(
        "--backends",
        default="bm25,semantic",
        help="Comma-separated backends to evaluate: bm25, semantic (default: both).",
    )
    parser.add_argument(
        "--k",
        default="5,10",
        help="Comma-separated k values for Recall@k (default: 5,10).",
    )
    parser.add_argument(
        "--embed-model",
        default="BAAI/bge-small-en-v1.5",
        help="Embedding model for semantic backend.",
    )
    parser.add_argument("--out", type=Path, default=None, help="Output JSON path.")
    parser.add_argument(
        "--limit", type=int, default=None, help="Cap the number of instances evaluated."
    )
    parser.add_argument(
        "--chunk-tokens",
        type=int,
        default=0,
        help=(
            "Chunk-level semantic retrieval window size in tokens. "
            "0 (default) uses plain semantic_rank (legacy, reproducible); "
            ">0 uses semantic_rank_chunked with this many tokens per chunk."
        ),
    )
    args = parser.parse_args(argv)

    data = _load_data(args.data)
    if data is None:
        print(f"note: could not load data from {args.data}")
        return 1

    ks = [int(k.strip()) for k in args.k.split(",") if k.strip()]
    requested = [b.strip() for b in args.backends.split(",") if b.strip()]

    if args.limit is not None:
        data = data[: args.limit]

    # Resolve which backends are actually runnable.
    embed_fn = None
    backends_to_run: list[str] = []

    if "semantic" in requested:
        embed_fn, available = _retrieval.semantic_backend_available(args.embed_model)
        if available:
            backends_to_run.append("semantic")
        else:
            print(
                "note: semantic backend unavailable (fastembed/sqlite_vec missing); "
                "skipping semantic arm"
            )

    if "bm25" in requested:
        backends_to_run.append("bm25")

    output: dict = {
        "benchmark": "longmemeval",
        "n_instances": 0,
        "skipped": 0,
        "embed_model": args.embed_model,
        "chunk_tokens": args.chunk_tokens,
        "backends": {},
    }

    for backend in backends_to_run:
        if backend == "bm25":
            ranker = lambda docs, q, k_: _retrieval.bm25_rank(docs, q, k_)  # noqa: E731
        elif args.chunk_tokens > 0:
            _ef = embed_fn
            _ct = args.chunk_tokens
            ranker = lambda docs, q, k_, __ef=_ef, __ct=_ct: _retrieval.semantic_rank_chunked(  # noqa: E731
                docs, q, k_, __ef, chunk_tokens=__ct
            )
        else:
            _ef = embed_fn
            ranker = lambda docs, q, k_, __ef=_ef: _retrieval.semantic_rank(docs, q, k_, __ef)  # noqa: E731

        results: list[dict] = []
        skipped = 0
        max_k = max(ks)

        for instance in data:
            gold = instance.get("answer_session_ids", [])
            if not gold:
                skipped += 1
                continue
            docs = _build_docs(instance)
            if docs is None:
                skipped += 1
                continue
            try:
                ranked = ranker(docs, instance.get("question", ""), max_k)
            except Exception:
                skipped += 1
                continue
            results.append({"ranked": ranked, "gold": gold})

        # Record n_instances and skipped from the last backend processed.
        # (Counts are dataset-level, not per-backend.)
        output["n_instances"] = len(results)
        output["skipped"] = skipped
        output["backends"][backend] = _aggregate(results, ks)

    # Console summary table.
    if output["backends"]:
        print(f"\n{'backend':<12} {'metric':<14} {'k':>4} {'mean':>8} {'wilson_ci':>22} {'n':>6}")
        print("-" * 70)
        for backend, metrics in output["backends"].items():
            for metric_name, k_data in metrics.items():
                for k_str, stats in k_data.items():
                    ci = f"[{stats['wilson_ci'][0]:.3f}, {stats['wilson_ci'][1]:.3f}]"
                    print(
                        f"{backend:<12} {metric_name:<14} {k_str:>4} "
                        f"{stats['mean']:>8.3f} {ci:>22} {stats['n']:>6}"
                    )

    if args.out is not None:
        try:
            args.out.write_text(json.dumps(output, indent=2))
        except Exception as exc:
            print(f"warning: could not write results to {args.out}: {exc}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
