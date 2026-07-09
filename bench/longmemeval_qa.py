"""LongMemEval QA-accuracy harness (Task B).

Implements a TRANSPARENT REPRODUCTION of the LongMemEval QA-accuracy headline metric
(session-level Recall@k retrieval → reader → judge → per-question-type accuracy).

Judge note: the default judge provider is "claude", which uses a SINGLE binary factcheck
judge (bench.grounding._factcheck) for ALL question types, NOT the paper's official
per-question-type GPT-4o judge prompts.  Pass --judge-provider openai to use a GPT-4o
judge (requires OPENAI_API_KEY and `pip install -e .[eval]`) for a paper-comparable
number.  The judge_model is configurable so callers can swap in a different model.
Abstention questions whose question_type ends in "_abs" use bench.grounding._judge_rejection
instead of _factcheck (the cleaned-S variant of the dataset uses question_type="abstention"
which does NOT end in "_abs"; that branch is defensive).

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
        --judge-provider openai \\
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
import bench.longmemeval as _lme

# Regex for parsing yes/no from OpenAI judge responses (case-insensitive, word-boundary).
_YESNO_OAI_RE = re.compile(r"\b(yes|no)\b", re.IGNORECASE)

# ─────────────────────────────────────────────────────────────────────────────
# LongMemEval-tuned reader instruction
# ─────────────────────────────────────────────────────────────────────────────

# Replaces grounding's generic "Answer concisely and specifically." for the LME reader.
# The {question_date} placeholder is filled per-instance from instance["question_date"].
# Required substrings (case-insensitive): "prior", "session", "only", "{question_date}".
_READER_INSTRUCTION = (
    "The context above is a set of the user's PRIOR CONVERSATION SESSIONS with an assistant. "
    "The question date is {question_date}. "
    "Answer using ONLY information present in those sessions. "
    "Be specific and concise. "
    "If the sessions do not contain the answer, say it is not available."
)

# ─────────────────────────────────────────────────────────────────────────────
# Lazy OpenAI seam (never raises — all errors surface as None/False)
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
            max_tokens=10,
        )
        return resp.choices[0].message.content
    except Exception:
        return None


def _judge_openai(question: str, gold: str, answer: str, model: str) -> bool | None:
    """Judge correctness using the OpenAI chat API; never raises.

    Builds a paper-style binary judge prompt and calls _openai_chat.
    Parses the first "yes"/"no" token from the response (case-insensitive).

    Args:
        question: The original question text.
        gold: The gold/correct answer string.
        answer: The model's answer to judge.
        model: OpenAI model name (e.g. "gpt-4o").

    Returns:
        True (correct), False (incorrect), or None (inconclusive/error).
    """
    try:
        system = "You are a strict grader."
        user = (
            "Is the model's ANSWER correct given the QUESTION and the correct/gold answer?\n"
            "Reply ONLY 'yes' or 'no'.\n\n"
            f"QUESTION: {question}\n"
            f"GOLD: {gold}\n"
            f"ANSWER: {answer}"
        )
        raw = _openai_chat(model, system, user)
        if raw is None:
            return None
        m = _YESNO_OAI_RE.search(raw)
        if not m:
            return None
        return m.group(1).lower() == "yes"
    except Exception:
        return None


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


def _answer_one(
    instance: dict,
    ids: list[str],
    reader_model: str,
    char_budget: int,
    *,
    provider: str = "claude",
) -> str:
    """Retrieve session texts for ids, build a context prefix, and call the reader model.

    Returns the reader's answer string, or "" on any failure (missing docs, LLM error,
    exception).  Never raises.

    For provider=="claude" (default): calls bench.grounding._answer with the LME-tuned
    _READER_INSTRUCTION (prior-session framing + question_date) via instruction= kwarg.
    For provider=="openai": routes through _openai_chat with the same tuned instruction
    embedded in the user message.

    Args:
        instance: A LongMemEval instance dict (must have haystack_session_ids/sessions).
        ids: Session ids to include as reader context (ranked or oracle).
        reader_model: Model name for the reader call.
        char_budget: Maximum chars to feed to the reader.
        provider: Reader provider — "claude" (default) or "openai".

    Returns:
        Answer string from the reader, or "" on failure.
    """
    try:
        docs = _lme._build_docs(instance)
        if docs is None:
            return ""
        context = _reader_context(docs, ids, char_budget=char_budget)
        instruction = _READER_INSTRUCTION.format(
            question_date=instance.get("question_date", "unknown")
        )
        if provider == "openai":
            system = "You are a helpful assistant that answers questions from conversation session context."
            user = f"{context}\n\nQUESTION: {instance['question']}\n\n{instruction}"
            return _openai_chat(reader_model, system, user) or ""
        return _g._answer(context, instance["question"], reader_model, instruction=instruction)
    except Exception:
        return ""


def _judge_one(
    answer: str, instance: dict, judge_model: str, *, provider: str = "claude"
) -> bool | None:
    """Judge whether answer correctly responds to the instance.

    For question types ending in "_abs" (abstention variant; defensive — cleaned-S has none),
    uses _g._judge_rejection to score whether the model appropriately declined.
    For provider=="openai", non-abstention questions use _judge_openai (GPT-4o judge).
    For provider=="claude" (default), non-abstention questions use _g._factcheck.

    A None return means the judge was inconclusive (no claude binary, parse error, etc.).

    Never raises.

    Args:
        answer: Reader model's answer string.
        instance: LongMemEval instance dict (must have question_type, question, answer keys).
        judge_model: Model name for the judge call.
        provider: Judge provider — "claude" (default) or "openai".

    Returns:
        True (correct), False (incorrect), or None (inconclusive).
    """
    try:
        if instance.get("question_type", "").endswith("_abs"):
            # Abstention path: correct iff the answer declines.
            # cleaned-S has no "_abs" question types — this branch is defensive.
            return _g._judge_rejection(answer, judge_model)
        if provider == "openai":
            return _judge_openai(instance["question"], instance["answer"], answer, judge_model)
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
        # Resolve effective judge model: openai provider defaults "sonnet" → "gpt-4o".
        judge_model = args.judge_model
        if args.judge_provider == "openai" and judge_model == "sonnet":
            judge_model = "gpt-4o"

        # Resolve effective reader model: openai provider defaults "sonnet" → "gpt-4-turbo".
        reader_provider = args.reader_provider
        effective_reader_model = args.reader_model
        if reader_provider == "openai" and effective_reader_model == "sonnet":
            effective_reader_model = "gpt-4-turbo"

        # Generalized openai use check — fires for judge OR reader openai use.
        use_openai = args.judge_provider == "openai" or reader_provider == "openai"

        # Hard-check: openai requires OPENAI_API_KEY and the openai package.
        # This is the ONE deliberate hard-stop — no silent fallback to claude.
        if use_openai and not (os.environ.get("OPENAI_API_KEY") and _openai_available()):
            print("--judge-provider openai requires OPENAI_API_KEY and `pip install -e .[eval]`")
            return 1

        # Upfront canary: one real probe per unique openai model before the scoring loop.
        # A None result means the key lacks access to that model — return 1 immediately
        # rather than silently scoring everything wrong.
        if use_openai:
            canary_models: set[str] = set()
            if args.judge_provider == "openai":
                canary_models.add(judge_model)
            if reader_provider == "openai":
                canary_models.add(effective_reader_model)
            for m in sorted(canary_models):
                raw = _openai_chat(m, "ping", "Reply with the single word: ok")
                if raw is None:
                    print(
                        f"openai canary failed for model '{m}' — check the key's project has "
                        f"access to that model; falling back is disabled to avoid silently "
                        f"scoring everything wrong"
                    )
                    return 1

        arms_requested = [a.strip() for a in args.arms.split(",") if a.strip()]

        # Run-level failure counters — tallied across all arms and instances.
        judge_none_count = 0
        reader_empty_count = 0

        # Sampling (sample first, then limit).
        # --sample draws a representative seeded random subset before --limit is applied.
        processed = list(instances)
        if args.sample is not None:
            processed = random.Random(args.seed).sample(processed, min(args.sample, len(processed)))
        if args.limit is not None:
            processed = processed[: args.limit]
        instances_to_score = processed

        # Build question_type_distribution over the scored instances.
        question_type_distribution: dict[str, int] = {}
        for inst in instances_to_score:
            qt = inst.get("question_type", "unknown")
            question_type_distribution[qt] = question_type_distribution.get(qt, 0) + 1

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

                    answer = _answer_one(
                        instance,
                        ids,
                        effective_reader_model,
                        args.char_budget,
                        provider=reader_provider,
                    )
                    judge = _judge_one(answer, instance, judge_model, provider=args.judge_provider)

                    # Tally failure signals independently (both may fire for the same item).
                    if answer == "":
                        reader_empty_count += 1
                    if judge is None:
                        judge_none_count += 1

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

        # Mass-failure guard: compute failure rate and unreliable flag BEFORE writing JSON.
        failure_rate = (judge_none_count + reader_empty_count) / max(1, total_n)
        unreliable = failure_rate > args.max_failure_rate

        output: dict = {
            "benchmark": "longmemeval_qa",
            "n_instances": len(instances_to_score),
            "limit": args.limit,
            "backend": args.backend,
            "k": args.k,
            "reader_model": effective_reader_model,
            "reader_provider": reader_provider,
            "judge_model": judge_model,
            "judge_provider": args.judge_provider,
            "sample": args.sample,
            "seed": args.seed,
            "question_type_distribution": question_type_distribution,
            "arms": arm_data,
            # Additive reliability keys — always present; byte-identical path sees 0/False.
            "unreliable": unreliable,
            "failure_rate": failure_rate,
            "judge_none": judge_none_count,
            "reader_empty": reader_empty_count,
        }

        if args.out is not None:
            try:
                args.out.write_text(json.dumps(output, indent=2))
            except Exception as exc:
                print(f"warning: could not write results to {args.out}: {exc}")

        # Console summary table
        print(
            f"\njudge_provider={args.judge_provider}  reader_provider={reader_provider}"
            f"  sample={args.sample}  seed={args.seed}"
        )
        print(f"\n{'arm':<12} {'type':<22} {'accuracy':>10} {'wilson_ci':>22} {'n':>6}")
        print("-" * 76)
        for arm_name, arm in arm_data.items():
            ov = arm["overall"]
            ci = f"[{ov['wilson_ci'][0]:.3f}, {ov['wilson_ci'][1]:.3f}]"
            print(f"{arm_name:<12} {'overall':<22} {ov['accuracy']:>10.3f} {ci:>22} {ov['n']:>6}")
            for qtype, stats in arm["by_type"].items():
                ci = f"[{stats['wilson_ci'][0]:.3f}, {stats['wilson_ci'][1]:.3f}]"
                print(f"{'':12} {qtype:<22} {stats['accuracy']:>10.3f} {ci:>22} {stats['n']:>6}")

        if total_n == 0:
            return 1
        if unreliable:
            print(
                f"\nWARNING: results UNRELIABLE — {failure_rate * 100:.1f}% of reader/judge calls "
                f"failed (empty answer or inconclusive judge), likely rate-limit/throttle "
                f"(e.g. low OpenAI TPM). Not a real score."
            )
            return 2
        return 0
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
        "--judge-provider",
        choices=("claude", "openai"),
        default="claude",
        help=(
            "Judge provider: 'claude' (default, uses bench.grounding._factcheck) or "
            "'openai' (GPT-4o judge for paper-comparable numbers; requires OPENAI_API_KEY "
            "and `pip install -e .[eval]`).  Leaving --judge-model at 'sonnet' with "
            "provider=openai auto-upgrades to 'gpt-4o'."
        ),
    )
    parser.add_argument(
        "--reader-provider",
        choices=("claude", "openai"),
        default="claude",
        help=(
            "Reader provider: 'claude' (default, uses bench.grounding._answer with the "
            "LME-tuned instruction) or 'openai' (routes through _openai_chat; requires "
            "OPENAI_API_KEY and `pip install -e .[eval]`). "
            "Leaving --reader-model at 'sonnet' with provider=openai auto-upgrades to "
            "'gpt-4-turbo'."
        ),
    )
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
    parser.add_argument(
        "--sample",
        type=int,
        default=None,
        help=(
            "Randomly sample N instances before --limit is applied (seeded by --seed). "
            "Produces a representative subset spanning question types."
        ),
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=0,
        help="Random seed for --sample (default: 0); ignored when --sample is not set.",
    )
    parser.add_argument("--out", type=Path, default=None, help="Output JSON path.")
    parser.add_argument(
        "--max-failure-rate",
        type=float,
        default=0.30,
        dest="max_failure_rate",
        help=(
            "Fraction of (reader-empty + judge-None) calls above which the run is declared "
            "UNRELIABLE (exit 2, unreliable:true in JSON). Default: 0.30. "
            "Useful when running under low-TPM OpenAI limits."
        ),
    )
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
