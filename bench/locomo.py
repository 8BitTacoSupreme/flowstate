"""LoCoMo evidence-coverage retrieval harness.

Compares FlowState's semantic backend (fastembed + sqlite-vec) against a BM25/FTS5
baseline on the LoCoMo benchmark (evidence-coverage retrieval metric).

Metrics (per the LoCoMo eval spec):
    coverage     = |gold_evidence ∩ retrieved_top_n| / |gold_evidence|  per qa
    full_coverage = 1 if gold_evidence ⊆ retrieved_top_n else 0         per qa
    mean_coverage      = mean(coverage) over non-skipped qa items
    full_coverage_rate = mean(full_coverage) over non-skipped qa items

QA items with empty evidence lists (abstentions) are skipped and counted.

Corpus arms (--corpus):
    turns        (default) retrieve over raw conversation turns (conv["conversation"]).
                 Byte-identical to prior behavior.
    observations retrieve over the paper's assertive observation summaries
                 (conv["observation"]), which carry dia_id provenance. Because
                 observation doc ids ARE dia_ids, evidence-coverage scoring is
                 unchanged and metric-compatible with the turns corpus.

    conv["session_summary"] (plain strings, no dia_id provenance) is intentionally
    NOT offered as a corpus arm: without dia_id provenance its docs cannot be scored
    by evidence-coverage (there is no id to intersect against gold evidence).

ADD-ONLY: do NOT modify bench/grounding.py or anything under flowstate/.

Usage:
    python -m bench.locomo \\
        --data <locomo_data.json> \\
        --backends bm25,semantic \\
        --corpus turns \\
        --top-n 5 \\
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
    """Load a LoCoMo JSON file. Never raises.

    Returns a non-empty list of conversation dicts on success, or None on any
    error (missing file, parse error, empty list, non-list result).
    """
    try:
        data = json.loads(Path(path).read_text())
        if not isinstance(data, list) or not data:
            return None
        return data
    except Exception:
        return None


def _build_docs(conv: dict) -> list[tuple[str, str]]:
    """Build (dia_id, text) doc list from all turns in a conversation. Never raises.

    Iterates over all session keys in conv['conversation'], skipping keys that
    end with '_date_time'.  Returns [] on any error.
    """
    try:
        docs: list[tuple[str, str]] = []
        conversation = conv.get("conversation", {})
        for key, value in conversation.items():
            if key.endswith("_date_time") or not isinstance(value, list):
                continue
            for turn in value:
                if isinstance(turn, dict) and "dia_id" in turn and "text" in turn:
                    docs.append((str(turn["dia_id"]), str(turn["text"])))
        return docs
    except Exception:
        return []


def _build_observation_docs(conv: dict) -> list[tuple[str, str]]:
    """Build (dia_id, text) doc list from observation summaries in a conversation.

    Iterates over conv['observation'][session_key][speaker], where each row is
    expected to be a 2-element [text, dia] list/tuple. If `dia` is a list of
    dia_ids, one doc is emitted per id (sharing the same text); if `dia` is a
    single id, one doc is emitted. Rows that don't match this shape (wrong type,
    wrong length) and non-dict session values are skipped. Never raises;
    returns [] on any error or when the 'observation' key is absent.

    Deduplication is intentionally NOT performed: if the same dia_id appears
    across multiple observation rows, each occurrence becomes its own doc.

    conv['session_summary'] is not a valid source for this builder: its values
    are plain strings with no dia_id provenance, so they cannot be scored by
    evidence-coverage (there is no id to intersect against gold evidence).
    """
    try:
        docs: list[tuple[str, str]] = []
        observation = conv.get("observation", {})
        if not isinstance(observation, dict):
            return []
        for session_value in observation.values():
            if not isinstance(session_value, dict):
                continue
            for rows in session_value.values():
                if not isinstance(rows, list):
                    continue
                for row in rows:
                    if not isinstance(row, list | tuple) or len(row) != 2:
                        continue
                    text, dia = row
                    if isinstance(dia, list):
                        for d in dia:
                            docs.append((str(d), str(text)))
                    else:
                        docs.append((str(dia), str(text)))
        return docs
    except Exception:
        return []


def _coverage(gold_evidence: list[str], retrieved_ids: list[str]) -> float:
    """Compute coverage = |gold ∩ retrieved| / |gold|.

    Returns 0.0 when gold_evidence is empty (caller should have skipped this qa).
    """
    if not gold_evidence:
        return 0.0
    intersection = set(gold_evidence) & set(retrieved_ids)
    return len(intersection) / len(gold_evidence)


def _full_coverage(gold_evidence: list[str], retrieved_ids: list[str]) -> int:
    """Returns 1 if all gold evidence ids are in retrieved_ids, else 0."""
    if not gold_evidence:
        return 0
    return 1 if set(gold_evidence).issubset(set(retrieved_ids)) else 0


def _aggregate(results: list[dict]) -> dict:
    """Aggregate coverage metrics over evaluated qa items.

    Args:
        results: List of dicts with keys 'coverage' and 'full_coverage'.

    Returns:
        Dict with mean_coverage, full_coverage_rate, wilson_ci, n.
    """
    n = len(results)
    if n == 0:
        return {
            "mean_coverage": 0.0,
            "full_coverage_rate": 0.0,
            "wilson_ci": [0.0, 0.0],
            "n": 0,
        }
    mean_cov = sum(r["coverage"] for r in results) / n
    full_successes = sum(r["full_coverage"] for r in results)
    full_rate = full_successes / n
    low, high = _wilson(full_successes, n)
    return {
        "mean_coverage": round(mean_cov, 4),
        "full_coverage_rate": round(full_rate, 4),
        "wilson_ci": [round(low, 4), round(high, 4)],
        "n": n,
    }


def main(argv: list[str] | None = None) -> int:
    """Run the LoCoMo retrieval benchmark. Returns 0 on success, 1 on error."""
    parser = argparse.ArgumentParser(
        prog="bench.locomo",
        description="LoCoMo evidence-coverage retrieval benchmark.",
    )
    parser.add_argument("--data", type=Path, required=True, help="Path to LoCoMo JSON file.")
    parser.add_argument(
        "--backends",
        default="bm25,semantic",
        help="Comma-separated backends to evaluate: bm25, semantic (default: both).",
    )
    parser.add_argument(
        "--corpus",
        choices=("turns", "observations"),
        default="turns",
        help="Retrieval corpus: raw conversation turns or observation summaries (default: turns).",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=5,
        help="Number of retrieved turns to consider (default: 5).",
    )
    parser.add_argument(
        "--embed-model",
        default="BAAI/bge-small-en-v1.5",
        help="Embedding model for semantic backend.",
    )
    parser.add_argument("--out", type=Path, default=None, help="Output JSON path.")
    parser.add_argument(
        "--limit", type=int, default=None, help="Cap the number of conversations evaluated."
    )
    args = parser.parse_args(argv)

    data = _load_data(args.data)
    if data is None:
        print(f"note: could not load data from {args.data}")
        return 1

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

    build_docs = _build_docs if args.corpus == "turns" else _build_observation_docs

    output: dict = {
        "benchmark": "locomo",
        "n_qa": 0,
        "skipped": 0,
        "top_n": args.top_n,
        "embed_model": args.embed_model,
        "corpus": args.corpus,
        "backends": {},
    }

    for backend in backends_to_run:
        if backend == "bm25":
            ranker = lambda docs, q, n_: _retrieval.bm25_rank(docs, q, n_)  # noqa: E731
        else:
            _ef = embed_fn
            ranker = lambda docs, q, n_, __ef=_ef: _retrieval.semantic_rank(docs, q, n_, __ef)  # noqa: E731

        all_results: list[dict] = []
        total_skipped = 0

        for conv in data:
            docs = build_docs(conv)
            for qa in conv.get("qa", []):
                evidence = qa.get("evidence", [])
                if not evidence:
                    total_skipped += 1
                    continue
                question = qa.get("question", "")
                try:
                    ranked = ranker(docs, question, args.top_n)
                except Exception:
                    total_skipped += 1
                    continue
                cov = _coverage(evidence, ranked)
                full_cov = _full_coverage(evidence, ranked)
                all_results.append({"coverage": cov, "full_coverage": full_cov})

        # Record counts from the last backend processed.
        output["n_qa"] = len(all_results)
        output["skipped"] = total_skipped
        output["backends"][backend] = _aggregate(all_results)

    # Console summary table.
    if output["backends"]:
        print(f"\ncorpus: {args.corpus}")
        print(f"{'backend':<12} {'mean_cov':>10} {'full_cov_rate':>14} {'wilson_ci':>22} {'n':>6}")
        print("-" * 68)
        for backend, stats in output["backends"].items():
            ci = f"[{stats['wilson_ci'][0]:.3f}, {stats['wilson_ci'][1]:.3f}]"
            print(
                f"{backend:<12} {stats['mean_coverage']:>10.3f} "
                f"{stats['full_coverage_rate']:>14.3f} {ci:>22} {stats['n']:>6}"
            )

    if args.out is not None:
        try:
            args.out.write_text(json.dumps(output, indent=2))
        except Exception as exc:
            print(f"warning: could not write results to {args.out}: {exc}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
