"""LongMemEval QA-accuracy harness (Task B).

Implements a TRANSPARENT REPRODUCTION of the LongMemEval QA-accuracy headline metric
(session-level Recall@k retrieval → reader → judge → per-question-type accuracy).

Judge note: this uses a SINGLE binary factcheck judge (bench.grounding._factcheck) for
ALL question types, NOT the paper's official per-question-type GPT-4o judge prompts.
The judge_model is configurable so callers can swap in a different model.  This approach
trades judge fidelity for operational simplicity; results are comparable within a run but
should not be compared directly to paper Table 2 numbers.  Abstention questions whose
question_type ends in "_abs" use bench.grounding._judge_rejection instead of _factcheck
(the cleaned-S variant of the dataset uses question_type="abstention" which does NOT end
in "_abs"; that branch is defensive).

ADD-ONLY: this module imports from bench.longmemeval, bench._retrieval, and bench.grounding
via module-attribute access so tests can monkeypatch any collaborator on its owning module.
Do NOT add from-imports for functions that callers need to patch.

Usage:
    python -m bench.longmemeval_qa \\
        --data <lme_data.json> \\
        --backend bm25 \\
        --arms retrieval,oracle \\
        --k 5 \\
        --limit 100 \\
        --out <results.json>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import bench._retrieval as _r
import bench.grounding as _g
import bench.longmemeval as _lme

# ─────────────────────────────────────────────────────────────────────────────
# Reader context builder
# ─────────────────────────────────────────────────────────────────────────────


def _reader_context(
    docs: list[tuple[str, str]],
    session_ids: list[str],
    *,
    char_budget: int = 48000,
) -> str:
    """Build a reader context string from selected sessions in the requested id order.

    Looks up each session_id in docs, joining their texts with "\\n\\n---\\n\\n" in the
    order given by session_ids (ids absent from docs are silently skipped).  The result
    is truncated to char_budget characters.  Returns "" on any error or when session_ids
    is empty.  Never raises.

    Args:
        docs: List of (session_id, session_text) pairs from _build_docs.
        session_ids: Ordered list of session ids to include in context.
        char_budget: Maximum character length of the returned string.

    Returns:
        Concatenated context string, truncated to char_budget chars.
    """
    try:
        id_to_text: dict[str, str] = {doc_id: text for doc_id, text in docs}
        texts = [id_to_text[sid] for sid in session_ids if sid in id_to_text]
        result = "\n\n---\n\n".join(texts)
        return result[:char_budget]
    except Exception:
        return ""


# ─────────────────────────────────────────────────────────────────────────────
# Per-instance answer + judge helpers
# ─────────────────────────────────────────────────────────────────────────────


def _answer_one(instance: dict, ids: list[str], reader_model: str, char_budget: int) -> str:
    """Retrieve session texts for ids, build a context prefix, and call the reader model.

    Returns the reader's answer string, or "" on any failure (missing docs, LLM error,
    exception).  Never raises.

    Args:
        instance: A LongMemEval instance dict (must have haystack_session_ids/sessions).
        ids: Session ids to include as reader context (ranked or oracle).
        reader_model: Model name passed to bench.grounding._answer.
        char_budget: Maximum chars to feed to the reader.

    Returns:
        Answer string from the reader, or "" on failure.
    """
    try:
        docs = _lme._build_docs(instance)
        if docs is None:
            return ""
        context = _reader_context(docs, ids, char_budget=char_budget)
        return _g._answer(context, instance["question"], reader_model)
    except Exception:
        return ""


def _judge_one(answer: str, instance: dict, judge_model: str) -> bool | None:
    """Judge whether answer correctly responds to the instance.

    For question types ending in "_abs" (abstention variant; defensive — cleaned-S has none),
    uses _g._judge_rejection to score whether the model appropriately declined.
    All other question types use _g._factcheck against instance["answer"] (the gold string).

    A None return means the judge was inconclusive (no claude binary, parse error, etc.).

    Never raises.

    Args:
        answer: Reader model's answer string.
        instance: LongMemEval instance dict (must have question_type and answer keys).
        judge_model: Model name for the judge call.

    Returns:
        True (correct), False (incorrect), or None (inconclusive).
    """
    try:
        if instance.get("question_type", "").endswith("_abs"):
            # Abstention path: correct iff the answer declines.
            # cleaned-S has no "_abs" question types — this branch is defensive.
            return _g._judge_rejection(answer, judge_model)
        return _g._factcheck(answer, instance["answer"], judge_model)
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Main evaluation loop
# ─────────────────────────────────────────────────────────────────────────────


def _run_qa(args: argparse.Namespace, instances: list[dict]) -> int:
    """Run the QA-accuracy evaluation over the given instances.

    Evaluates one or more arms ("retrieval", "oracle") and aggregates accuracy
    per question_type and overall, with Wilson score confidence intervals.

    A None judge result is INCORRECT (correct only when judge is True) but IS
    counted in n, so abstentions/failures lower accuracy without being silently
    dropped.

    Never raises — the outer try/except returns 1 on any unexpected failure.

    Args:
        args: Parsed argument namespace (see _build_parser for attribute list).
        instances: List of LongMemEval instance dicts to evaluate.

    Returns:
        0 on success (at least one instance scored), 1 when zero instances scored
        or any unrecoverable error.
    """
    try:
        arms_requested = [a.strip() for a in args.arms.split(",") if a.strip()]

        # Apply limit
        instances_to_score = instances[: args.limit] if args.limit is not None else instances

        arm_data: dict[str, dict] = {}

        for arm_name in arms_requested:
            if arm_name not in {"retrieval", "oracle"}:
                continue

            per_type_correct: dict[str, int] = {}
            per_type_n: dict[str, int] = {}
            overall_correct = 0
            overall_n = 0

            # Resolve semantic backend ONCE before the instance loop (Task A parity).
            embed_fn = None
            if arm_name == "retrieval" and args.backend == "semantic":
                embed_fn, available = _r.semantic_backend_available(args.embed_model)
                if not available:
                    print(
                        "note: semantic backend unavailable (fastembed/sqlite_vec missing); "
                        "skipping retrieval arm"
                    )
                    continue

            for instance in instances_to_score:
                try:
                    q = instance.get("question", "")
                    qtype = instance.get("question_type", "unknown")

                    if arm_name == "retrieval":
                        docs = _lme._build_docs(instance)
                        if docs is None:
                            continue
                        if args.backend == "bm25":
                            ids: list[str] = _r.bm25_rank(docs, q, args.k)
                        else:  # semantic — embed_fn resolved above
                            ids = _r.semantic_rank(docs, q, args.k, embed_fn)
                    else:  # oracle
                        ids = instance.get("answer_session_ids", [])

                    answer = _answer_one(instance, ids, args.reader_model, args.char_budget)
                    judge = _judge_one(answer, instance, args.judge_model)

                    # None judge is INCORRECT (correct only when True) but IS counted in n.
                    per_type_n[qtype] = per_type_n.get(qtype, 0) + 1
                    if qtype not in per_type_correct:
                        per_type_correct[qtype] = 0
                    overall_n += 1
                    if judge is True:
                        per_type_correct[qtype] += 1
                        overall_correct += 1
                except Exception:
                    continue

            # Build per-type stats blocks
            by_type: dict[str, dict] = {}
            for qtype, n in per_type_n.items():
                correct = per_type_correct.get(qtype, 0)
                acc = correct / n if n else 0.0
                low, high = _g._wilson(correct, n)
                by_type[qtype] = {"accuracy": acc, "n": n, "wilson_ci": [low, high]}

            # Build overall stats block
            low, high = _g._wilson(overall_correct, overall_n)
            overall_acc = overall_correct / overall_n if overall_n else 0.0
            arm_data[arm_name] = {
                "overall": {
                    "accuracy": overall_acc,
                    "n": overall_n,
                    "wilson_ci": [low, high],
                },
                "by_type": by_type,
            }

        # Return 1 when zero instances were scored across all arms.
        total_n = sum(arm_data[arm]["overall"]["n"] for arm in arm_data)

        output: dict = {
            "benchmark": "longmemeval_qa",
            "n_instances": len(instances_to_score),
            "limit": args.limit,
            "backend": args.backend,
            "k": args.k,
            "reader_model": args.reader_model,
            "judge_model": args.judge_model,
            "arms": arm_data,
        }

        if args.out is not None:
            try:
                args.out.write_text(json.dumps(output, indent=2))
            except Exception as exc:
                print(f"warning: could not write results to {args.out}: {exc}")

        # Console summary table
        print(f"\n{'arm':<12} {'type':<22} {'accuracy':>10} {'wilson_ci':>22} {'n':>6}")
        print("-" * 76)
        for arm_name, arm in arm_data.items():
            ov = arm["overall"]
            ci = f"[{ov['wilson_ci'][0]:.3f}, {ov['wilson_ci'][1]:.3f}]"
            print(f"{arm_name:<12} {'overall':<22} {ov['accuracy']:>10.3f} {ci:>22} {ov['n']:>6}")
            for qtype, stats in arm["by_type"].items():
                ci = f"[{stats['wilson_ci'][0]:.3f}, {stats['wilson_ci'][1]:.3f}]"
                print(f"{'':12} {qtype:<22} {stats['accuracy']:>10.3f} {ci:>22} {stats['n']:>6}")

        return 1 if total_n == 0 else 0
    except Exception:
        return 1


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser for bench.longmemeval_qa."""
    parser = argparse.ArgumentParser(
        prog="bench.longmemeval_qa",
        description=(
            "LongMemEval QA-accuracy harness (Task B): "
            "retrieve sessions → read → judge → per-type accuracy."
        ),
    )
    parser.add_argument("--data", type=Path, required=True, help="Path to LongMemEval JSON file.")
    parser.add_argument(
        "--backend",
        choices=("bm25", "semantic"),
        default="semantic",
        help="Retrieval backend for the retrieval arm (default: semantic).",
    )
    parser.add_argument("--k", type=int, default=5, help="Top-k sessions to retrieve (default: 5).")
    parser.add_argument(
        "--arms",
        default="retrieval",
        help="Comma-separated arms to evaluate: retrieval, oracle (default: retrieval).",
    )
    parser.add_argument("--reader-model", default="sonnet", help="Model for reading/answering.")
    parser.add_argument("--judge-model", default="sonnet", help="Model for fact-checking.")
    parser.add_argument(
        "--embed-model",
        default="BAAI/bge-small-en-v1.5",
        help="Embedding model for semantic backend.",
    )
    parser.add_argument(
        "--char-budget",
        type=int,
        default=48000,
        help="Max characters fed to the reader model (default: 48000).",
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="Cap the number of instances evaluated."
    )
    parser.add_argument("--out", type=Path, default=None, help="Output JSON path.")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the LongMemEval QA-accuracy harness. Returns 0 on success, 1 on error."""
    args = _build_parser().parse_args(argv)
    instances = _lme._load_data(args.data)
    if instances is None:
        print(f"note: could not load data from {args.data}")
        return 1
    return _run_qa(args, instances)


if __name__ == "__main__":
    sys.exit(main())
