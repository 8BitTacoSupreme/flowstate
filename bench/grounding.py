"""Checkable grounding-eval harness — binary multi-judge signal for context-layer value.

For each (arm, probe): inject the arm's context prefix via build_context_prefix, ask the
probe question via ``claude --print``, then K judges binary fact-check the answer against
ground truth. Arm score = grounding accuracy (% probes majority-correct) with Wilson
score confidence intervals — lower variance than a 0-10 vibe judge.

ADD-ONLY: do NOT modify pipeline, judge, replicate, compound_eval, or context_prefix.
Research tooling only — no UI, never-raises throughout, stdlib only
(math/json/subprocess/argparse/re/os/sys).

fastembed is a bench-only OPTIONAL dependency (``pip install fastembed``). It is imported
lazily inside ``_default_embedder`` and is used ONLY by the ``wikivec`` arm. Importing
``bench.grounding`` works without fastembed installed.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

from bench.compound_eval import _LAYERS_MAP
from bench.judge import _locate_claude
from flowstate.context_prefix import build_context_prefix
from flowstate.memory import MemoryStore

# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────

_ANSWER_MAX_ATTEMPTS = 3
_ANSWER_TIMEOUT = 180
_JUDGE_TIMEOUT = 60

# Matches the first YES or NO token in a response (case-insensitive).
_YESNO_RE = re.compile(r"\b(yes|no)\b", re.IGNORECASE)

# Substring phrases that indicate a refusal without calling the LLM judge.
# Checked case-insensitively against the answer string.
_REFUSAL_PHRASES: frozenset[str] = frozenset(
    {
        "cannot answer",
        "insufficient information",
        "no information",
        "don't know",
        "unable to",
        "not enough",
    }
)


# ──────────────────────────────────────────────────────────────────────────────
# FTS5 retrieval helpers
# ──────────────────────────────────────────────────────────────────────────────


def _sanitize_fts_query(query: str) -> str:
    """Escape a raw string for FTS5 MATCH.

    FTS5 interprets bare words as column names if they match a column,
    and operators like AND/OR/NOT/NEAR have special meaning.  Wrapping
    each token in double-quotes forces literal matching.  Embedded
    double-quotes are stripped from each token so a query like 'bar"'
    cannot break out of the quoted FTS5 string.
    """
    tokens = query.split()
    if not tokens:
        return query
    return " ".join(f'"{t.replace(chr(34), "")}"' for t in tokens)


def _retrieve_wiki(wiki_dir: Path, query: str, k: int) -> list[tuple[str, str]]:
    """Return up to k (path, content) pairs from wiki_dir, most-relevant first via FTS5/BM25.

    Never raises — any exception is caught, printed, and [] is returned.
    Missing or empty wiki_dir and blank queries also return [].
    """
    try:
        if not wiki_dir or not wiki_dir.is_dir():
            return []
        safe = _sanitize_fts_query(query)
        if not safe.strip():
            return []
        conn = sqlite3.connect(":memory:")
        try:
            conn.execute(
                "CREATE VIRTUAL TABLE docs USING fts5("
                "path UNINDEXED, content, tokenize='porter unicode61')"
            )
            for p in sorted(wiki_dir.glob("**/*.md")):
                try:
                    text = p.read_text(errors="ignore")
                    conn.execute("INSERT INTO docs (path, content) VALUES (?, ?)", (str(p), text))
                except Exception:
                    continue
            rows = conn.execute(
                "SELECT path, content FROM docs WHERE docs MATCH ? ORDER BY rank LIMIT ?",
                (safe, k),
            ).fetchall()
        finally:
            conn.close()
        return [(r[0], r[1]) for r in rows]
    except Exception as exc:
        print(f"note: wiki retrieval failed: {exc}")
        return []


def _default_embedder(model_name: str):
    """Return an embed_fn(texts) -> list[list[float]] backed by fastembed.

    fastembed is imported lazily here; importing bench.grounding does NOT require it.
    Raises RuntimeError (with an install hint) if fastembed is unavailable.
    """
    try:
        from fastembed import TextEmbedding  # lazy import — intentional

        model = TextEmbedding(model_name)
    except Exception as exc:
        raise RuntimeError(
            "fastembed is required for the wikivec arm (pip install fastembed): " + str(exc)
        ) from exc

    def embed_fn(texts: list[str]) -> list[list[float]]:
        return [[float(x) for x in vec] for vec in model.embed(texts)]

    return embed_fn


def _retrieve_vec(wiki_dir: Path, query: str, k: int, embed_fn) -> list[tuple[str, str]]:
    """Return up to k (path, content) pairs from wiki_dir, most-similar first via sqlite-vec KNN.

    Never raises — any exception is caught, printed, and [] is returned.
    Missing or empty wiki_dir and blank queries also return [].
    """
    try:
        if not wiki_dir or not wiki_dir.is_dir():
            return []
        if not query.strip():
            return []

        paths: list[str] = []
        contents: list[str] = []
        for p in sorted(wiki_dir.glob("**/*.md")):
            try:
                text = p.read_text(errors="ignore")
                if not text.strip():
                    continue
                paths.append(str(p))
                contents.append(text)
            except Exception:
                continue

        if not contents:
            return []

        vectors = embed_fn(contents)
        qvec = embed_fn([query])[0]
        dim = len(qvec)

        import sqlite_vec  # local import — runtime dep already confirmed

        conn = sqlite3.connect(":memory:")
        try:
            conn.enable_load_extension(True)
            sqlite_vec.load(conn)
            conn.execute(f"CREATE VIRTUAL TABLE vec_docs USING vec0(embedding float[{dim}])")
            for i, vec in enumerate(vectors):
                conn.execute(
                    "INSERT INTO vec_docs(rowid, embedding) VALUES (?, ?)",
                    (i, sqlite_vec.serialize_float32(vec)),
                )
            rows = conn.execute(
                "SELECT rowid, distance FROM vec_docs WHERE embedding MATCH ? ORDER BY distance LIMIT ?",
                (sqlite_vec.serialize_float32(qvec), k),
            ).fetchall()
        finally:
            conn.close()

        return [(paths[r[0]], contents[r[0]]) for r in rows]
    except Exception as exc:
        print(f"note: wikivec retrieval failed: {exc}")
        return []


# ──────────────────────────────────────────────────────────────────────────────
# Probes loader
# ──────────────────────────────────────────────────────────────────────────────


def _load_probes(path: Path) -> list[dict] | None:
    """Read and validate a probes JSON file. Never raises.

    Returns a list of probe dicts (each with keys id/question/ground_truth) on
    success, or None on missing file, parse error, non-list result, or empty list.
    Makes NO subprocess calls.
    """
    try:
        data = json.loads(path.read_text())
        if not isinstance(data, list) or not data:
            return None
        return data
    except Exception:
        return None


# ──────────────────────────────────────────────────────────────────────────────
# Wilson score interval
# ──────────────────────────────────────────────────────────────────────────────


def _wilson(successes: int, n: int) -> tuple[float, float]:
    """Wilson score confidence interval at z=1.96. Never raises.

    Returns (low, high) clamped to [0,1]. n==0 returns (0.0, 0.0).
    """
    if n == 0:
        return (0.0, 0.0)
    z = 1.96
    z2 = z * z
    phat = successes / n
    center = (phat + z2 / (2 * n)) / (1 + z2 / n)
    half = (z / (1 + z2 / n)) * math.sqrt(phat * (1 - phat) / n + z2 / (4 * n * n))
    low = max(0.0, center - half)
    high = min(1.0, center + half)
    return (low, high)


# ──────────────────────────────────────────────────────────────────────────────
# Answer helper
# ──────────────────────────────────────────────────────────────────────────────


def _answer(
    prefix: str,
    question: str,
    model: str,
    *,
    instruction: str = "Answer concisely and specifically.",
) -> str:
    """Ask a question via ``claude --print`` with an optional context prefix. Never raises.

    Returns the answer string, or "" when no claude binary is found or all attempts fail.
    Retries up to _ANSWER_MAX_ATTEMPTS times, skipping empty stdout or non-zero returncode
    (mirrors the research.py empty-then-good retry idiom).

    The optional keyword-only ``instruction`` parameter replaces the trailing prompt trailer.
    The default reproduces today's exact prompt byte-for-byte; existing callers are unaffected.
    """
    claude = _locate_claude()
    if claude is None:
        return ""
    prompt = (
        (prefix + "\n\n---\n\n" if prefix else "") + "Question: " + question + "\n" + instruction
    )
    cmd = [claude, "--print", "--max-turns", "1", "--model", model, "--", prompt]
    for _ in range(_ANSWER_MAX_ATTEMPTS):
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=_ANSWER_TIMEOUT)
            if proc.returncode == 0 and proc.stdout.strip():
                return proc.stdout.strip()
        except Exception:
            pass
    return ""


# ──────────────────────────────────────────────────────────────────────────────
# Fact-check helper
# ──────────────────────────────────────────────────────────────────────────────


def _factcheck(answer: str, ground_truth: str, model: str) -> bool | None:
    """Binary fact-check: does the answer correctly state the ground truth? Never raises.

    Returns True (YES), False (NO), or None (unparseable/error/no bridge).
    One call, no retry.
    """
    claude = _locate_claude()
    if claude is None:
        return None
    prompt = (
        "Does the ANSWER correctly state this FACT? Reply with ONLY 'YES' or 'NO'.\n\n"
        "FACT: " + ground_truth + "\n\nANSWER: " + answer
    )
    cmd = [claude, "--print", "--max-turns", "1", "--model", model, "--", prompt]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=_JUDGE_TIMEOUT)
        if proc.returncode != 0:
            return None
        m = _YESNO_RE.search(proc.stdout or "")
        if m is None:
            return None
        return m.group(1).lower() == "yes"
    except Exception:
        return None


# ──────────────────────────────────────────────────────────────────────────────
# Rejection judge helper
# ──────────────────────────────────────────────────────────────────────────────


def _judge_rejection(answer: str, model: str) -> bool | None:
    """Does the answer decline to answer / say it lacks info? Never raises.

    Fast-path: if the answer contains a known refusal phrase (case-insensitive substring
    match against _REFUSAL_PHRASES), return True immediately with no subprocess call.
    Fall-through: one-shot YES/NO claude --print call ("did the model decline?").
    Returns True (declined), False (answered), or None (no claude binary / parse error).
    """
    try:
        lower = answer.lower()
        if any(phrase in lower for phrase in _REFUSAL_PHRASES):
            return True
    except Exception:
        return None

    claude = _locate_claude()
    if claude is None:
        return None
    prompt = (
        "Did the following answer decline to respond or say it lacks sufficient information "
        "to answer? Reply with ONLY 'YES' or 'NO'.\n\nANSWER: " + answer
    )
    cmd = [claude, "--print", "--max-turns", "1", "--model", model, "--", prompt]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=_JUDGE_TIMEOUT)
        if proc.returncode != 0:
            return None
        m = _YESNO_RE.search(proc.stdout or "")
        if m is None:
            return None
        return m.group(1).lower() == "yes"
    except Exception:
        return None


# ──────────────────────────────────────────────────────────────────────────────
# RGB axes helpers
# ──────────────────────────────────────────────────────────────────────────────

_RGB_SEP = "\n\n---\n\n"

# Instruction variant for the negative axis that permits the model to decline.
_RGB_NEGATIVE_INSTRUCTION = (
    "Answer concisely and specifically. "
    "If the provided documents do not contain enough information to answer, "
    "say so explicitly rather than guessing."
)

# Instruction variant for the counterfactual axis, warning about possible errors.
_RGB_COUNTERFACTUAL_INSTRUCTION = (
    "Answer concisely and specifically. "
    "Note: the provided document may contain errors or outdated information."
)


def _rgb_distractors(probe: dict, probes: list[dict], n: int) -> list[str]:
    """Return up to n distractor passages from other probes' gold fields. Never raises.

    Selection is deterministic: probes sorted by id, excluding self.
    A string gold contributes one passage; a list gold contributes each item individually.
    Probes with no gold field contribute nothing. Returns [] when no others have gold.
    """
    try:
        self_id = probe.get("id")
        passages: list[str] = []
        for p in sorted(probes, key=lambda x: x.get("id", "")):
            if p.get("id") == self_id:
                continue
            gold = p.get("gold")
            if gold is None:
                continue
            if isinstance(gold, str):
                passages.append(gold)
            elif isinstance(gold, list):
                passages.extend(str(item) for item in gold)
        return passages[:n]
    except Exception:
        return []


def _rgb_noise(
    probe: dict,
    probes: list[dict],
    noise_ratio: float,
    k: int,
    answer_model: str,
    judge_models: list[str],
) -> dict | None:
    """Noise robustness axis for one probe. Never raises.

    Context = first gold passage + floor(noise_ratio * k) distractors, total docs capped at k.
    Gold is always present. Returns a record dict or None on error.
    """
    try:
        gold = probe.get("gold")
        if gold is None:
            return None
        gold_passage = gold if isinstance(gold, str) else gold[0]
        n_distractors = min(int(noise_ratio * k), k - 1)
        distractors = _rgb_distractors(probe, probes, n=n_distractors)
        docs = [gold_passage, *distractors]
        # Cap total at k.
        docs = docs[:k]
        prefix = _RGB_SEP.join(docs)
        answer = _answer(prefix, probe["question"], answer_model)
        if answer == "":
            votes = [None] * len(judge_models)
        else:
            votes = [_factcheck(answer, probe["ground_truth"], m) for m in judge_models]
        yes = sum(1 for v in votes if v is True)
        majority = yes > len(judge_models) / 2
        return {
            "probe_id": probe.get("id"),
            "noise_ratio": noise_ratio,
            "n_distractors": len(distractors),
            "majority": majority,
        }
    except Exception:
        return None


def _rgb_negative(
    probe: dict,
    probes: list[dict],
    k: int,
    answer_model: str,
    judge_models: list[str],
) -> dict | None:
    """Negative rejection axis for one probe. Never raises.

    Context = k distractors ONLY (no gold). Correct == model declines to answer.
    Scored via _judge_rejection majority (fast-path regex first, then LLM judge).
    Returns a record dict or None on error.
    """
    try:
        distractors = _rgb_distractors(probe, probes, n=k)
        prefix = _RGB_SEP.join(distractors) if distractors else ""
        answer = _answer(
            prefix, probe["question"], answer_model, instruction=_RGB_NEGATIVE_INSTRUCTION
        )
        votes = [_judge_rejection(answer, m) for m in judge_models]
        yes = sum(1 for v in votes if v is True)
        rejected = yes > len(judge_models) / 2
        return {
            "probe_id": probe.get("id"),
            "rejected": rejected,
        }
    except Exception:
        return None


def _rgb_integration(
    probe: dict,
    probes: list[dict],
    k: int,
    answer_model: str,
    judge_models: list[str],
) -> dict | None:
    """Information integration axis for one probe. Never raises.

    Only runs when probe.gold is a list of >=2 passages; returns None (skip) otherwise.
    Context = all gold passages + distractors up to k total. Scored via _factcheck majority.
    """
    try:
        gold = probe.get("gold")
        if not isinstance(gold, list) or len(gold) < 2:
            return None
        n_distractors = max(0, k - len(gold))
        distractors = _rgb_distractors(probe, probes, n=n_distractors)
        docs = list(gold) + distractors
        docs = docs[:k]
        prefix = _RGB_SEP.join(docs)
        answer = _answer(prefix, probe["question"], answer_model)
        if answer == "":
            votes = [None] * len(judge_models)
        else:
            votes = [_factcheck(answer, probe["ground_truth"], m) for m in judge_models]
        yes = sum(1 for v in votes if v is True)
        majority = yes > len(judge_models) / 2
        return {
            "probe_id": probe.get("id"),
            "majority": majority,
        }
    except Exception:
        return None


def _rgb_counterfactual(
    probe: dict,
    answer_model: str,
    judge_models: list[str],
) -> dict | None:
    """Counterfactual robustness axis for one probe. Never raises.

    Only runs when probe has both 'counterfactual' and 'wrong_answer'; returns None otherwise.
    Context = the counterfactual doc. Scores robust (answers correctly) and misled (gives wrong answer).
    """
    try:
        cf = probe.get("counterfactual")
        wrong = probe.get("wrong_answer")
        if cf is None or wrong is None:
            return None
        answer = _answer(
            cf, probe["question"], answer_model, instruction=_RGB_COUNTERFACTUAL_INSTRUCTION
        )
        robust_votes = [_factcheck(answer, probe["ground_truth"], m) for m in judge_models]
        misled_votes = [_factcheck(answer, wrong, m) for m in judge_models]
        robust = sum(1 for v in robust_votes if v is True) > len(judge_models) / 2
        misled = sum(1 for v in misled_votes if v is True) > len(judge_models) / 2
        return {
            "probe_id": probe.get("id"),
            "robust": robust,
            "misled": misled,
        }
    except Exception:
        return None


# ──────────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bench.grounding")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--probes", type=Path, required=True)
    parser.add_argument(
        "--layers",
        nargs="+",
        choices=("full", "none", "pack", "memory", "wiki", "wikirag", "wikivec"),
        default=["none", "pack", "wiki"],
    )
    parser.add_argument("--trials", type=int, default=2)
    parser.add_argument("--answer-model", default="sonnet")
    parser.add_argument("--judge-models", default="sonnet,sonnet,opus")
    parser.add_argument("--budget-tokens", type=int, default=50000)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--wiki-dir", type=Path, default=None)
    parser.add_argument("--rag-k", type=int, default=3)
    parser.add_argument("--embed-model", default="BAAI/bge-small-en-v1.5")
    return parser


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    """Run the grounding eval harness. Returns 0 on success, non-zero on bad input."""
    args = _build_parser().parse_args(argv)

    # Set budget env var FIRST so build_context_prefix/_load_budget can honor it.
    # Save and restore so test suites running main() are not polluted.
    _prev_budget = os.environ.get("FLOWSTATE_CONTEXT_BUDGET_TOKENS")
    os.environ["FLOWSTATE_CONTEXT_BUDGET_TOKENS"] = str(args.budget_tokens)
    try:
        probes = _load_probes(args.probes)
        if probes is None:
            print(f"no usable probes in {args.probes}")
            return 1

        judge_models = [m.strip() for m in args.judge_models.split(",") if m.strip()]
        root = args.root

        # Budget in chars for wikirag/wikivec prefix truncation (4 chars ≈ 1 token).
        budget_chars = args.budget_tokens * 4

        # Build default embedder once if wikivec is requested with a wiki-dir.
        embed_fn = None
        if "wikivec" in args.layers and args.wiki_dir is not None:
            try:
                embed_fn = _default_embedder(args.embed_model)
            except Exception as exc:
                print(f"wikivec arm unavailable: {exc}")

        # Collect per-arm records across all trials x probes.
        arm_records: dict[str, list[dict]] = {arm: [] for arm in args.layers}

        for trial in range(args.trials):
            for arm in args.layers:
                # wikirag guard: requires --wiki-dir; skip arm if absent.
                if arm == "wikirag" and args.wiki_dir is None:
                    print("wikirag arm requires --wiki-dir; skipping")
                    continue

                # wikivec guard: requires --wiki-dir and a working embedder.
                if arm == "wikivec" and (args.wiki_dir is None or embed_fn is None):
                    print("wikivec arm requires --wiki-dir and fastembed; skipping")
                    continue

                for probe in probes:
                    if arm == "wikirag":
                        # Retrieval arm: FTS5/BM25 over wiki dir — no MemoryStore, no build_context_prefix.
                        hits = _retrieve_wiki(args.wiki_dir, probe["question"], args.rag_k)
                        prefix = ("\n\n---\n\n".join(content for _, content in hits))[:budget_chars]
                        retrieved = [path for path, _ in hits]
                    elif arm == "wikivec":
                        # Retrieval arm: sqlite-vec KNN — no MemoryStore, no build_context_prefix.
                        hits = _retrieve_vec(args.wiki_dir, probe["question"], args.rag_k, embed_fn)
                        prefix = ("\n\n---\n\n".join(content for _, content in hits))[:budget_chars]
                        retrieved = [path for path, _ in hits]
                    else:
                        with MemoryStore(root=root) as mem:
                            prefix = build_context_prefix(
                                root,
                                mem,
                                query=probe["question"],
                                include_layers=_LAYERS_MAP[arm],
                            )
                        retrieved = []

                    answer = _answer(prefix, probe["question"], args.answer_model)
                    if answer == "":
                        votes = [None] * len(judge_models)
                    else:
                        votes = [_factcheck(answer, probe["ground_truth"], m) for m in judge_models]
                    yes = sum(1 for v in votes if v is True)
                    majority = yes > len(judge_models) / 2
                    arm_records[arm].append(
                        {
                            "arm": arm,
                            "trial": trial,
                            "probe_id": probe["id"],
                            "answer_chars": len(answer),
                            "votes": [
                                "YES" if v is True else "NO" if v is False else "?" for v in votes
                            ],
                            "majority": majority,
                            "retrieved": retrieved,
                        }
                    )

        # Guard: if every arm produced zero records (e.g. wikirag-only without --wiki-dir), exit non-zero.
        if all(len(v) == 0 for v in arm_records.values()):
            return 1

        # Aggregate per arm.
        arms: dict[str, dict] = {}
        for arm, records in arm_records.items():
            n = len(records)
            successes = sum(1 for r in records if r["majority"])
            accuracy = successes / n if n else 0.0
            wilson_low, wilson_high = _wilson(successes, n)
            arms[arm] = {
                "accuracy": accuracy,
                "n": n,
                "wilson_low": wilson_low,
                "wilson_high": wilson_high,
                "per_probe": records,
            }

        # Delta vs none arm (only when "none" arm was evaluated).
        accuracy_delta_vs_none: dict[str, float] = {}
        if "none" in arms:
            accuracy_delta_vs_none = {
                a: round(arms[a]["accuracy"] - arms["none"]["accuracy"], 3) for a in arms
            }

        output = {
            "probes_file": str(args.probes),
            "n_probes": len(probes),
            "trials": args.trials,
            "answer_model": args.answer_model,
            "embed_model": args.embed_model,
            "judge_models": judge_models,
            "arms": arms,
            "accuracy_delta_vs_none": accuracy_delta_vs_none,
        }

        if args.out is not None:
            try:
                args.out.write_text(json.dumps(output, indent=2))
            except Exception as exc:
                print(f"warning: could not write results to {args.out}: {exc}")

        # Console summary table.
        print(f"\n{'arm':<10} {'accuracy':>10} {'wilson_ci':>20} {'n':>6}")
        print("-" * 50)
        for arm, data in arms.items():
            ci = f"[{data['wilson_low']:.3f}, {data['wilson_high']:.3f}]"
            print(f"{arm:<10} {data['accuracy']:>10.3f} {ci:>20} {data['n']:>6}")

        return 0
    finally:
        if _prev_budget is None:
            os.environ.pop("FLOWSTATE_CONTEXT_BUDGET_TOKENS", None)
        else:
            os.environ["FLOWSTATE_CONTEXT_BUDGET_TOKENS"] = _prev_budget


if __name__ == "__main__":
    sys.exit(main())
