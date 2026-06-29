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

RGB mode (``--mode rgb``)
--------------------------
An additive adversarial-context evaluation across four axes.  The arm loop (layers mode)
is completely unaffected when ``--mode`` is absent or ``layers``.  RGB requires NO
fastembed or sqlite_vec — it is stdlib-only and works offline in tests.

Axes (selected via ``--axes``, default = all four):

noise
    Measures robustness when distractors are injected alongside the gold passage.
    Context = 1 gold passage + floor(noise_ratio * k) distractors, total capped at k.
    Gold is ALWAYS present.  Swept over ``--noise-ratios`` (default ``0.0,0.4,0.8``).
    Output: per_ratio dict keyed by ratio string → {accuracy, n, wilson_ci}.

negative
    Measures ability to decline when no gold passage is provided.
    Context = k distractors only (no gold).  Correct == model refuses to answer.
    Scored via _judge_rejection (regex fast-path for common refusal phrases; LLM judge
    as fallback).  Output: {rejection_rate, n, wilson_ci}.

integration
    Measures multi-hop reasoning when gold is split across multiple passages.
    Only runs on probes whose ``gold`` field is a list of >=2 passages; others are
    skipped and logged.  Context = all gold passages + distractors up to k.
    Output: {accuracy, n, wilson_ci, skipped}.

counterfactual
    Measures resilience to misleading context.  Only runs on probes with both
    ``counterfactual`` and ``wrong_answer`` fields; others are skipped.
    Context = the counterfactual doc.  Scores robust (answers correctly despite
    misleading doc) and misled (answers with the wrong answer).
    Output: {robust_rate, misled_rate, n, wilson_ci, skipped}.

Extended probe schema (all new fields are optional; existing required fields unchanged):
    gold (str | list[str])  — one or more gold passages for noise/negative/integration axes.
    counterfactual (str)    — a misleading document for the counterfactual axis.
    wrong_answer (str)      — the incorrect answer the misleading doc would induce.

``--hard-negatives`` (opt-in): reorders distractors topically-nearest-first via the
existing embedder (``--embed-model``). Soft-fails to id-order when fastembed is
unavailable. RGB-mode only; reuses ``--embed-model``; recorded as ``hard_negatives``
boolean in the RGB JSON output.

See bench/fixtures/rgb_probes.example.json for a complete example probe list.
"""

from __future__ import annotations

import argparse
import hashlib
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
from flowstate.bridge import BridgeConfig, ClaudeBridge
from flowstate.context_prefix import build_context_prefix
from flowstate.memory import MemoryStore
from flowstate.state import InterviewAnswers
from flowstate.tools.strategy import STRATEGY_SYSTEM_PROMPT, _build_pressure_test_prompt

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


def _rank_by_similarity(query: str, candidates: list[str], embed_fn) -> list[str]:
    """Return candidates reordered nearest-first by cosine similarity to query.

    Makes exactly one embed_fn([query] + candidates) call. Computes cosine in pure Python
    (math module only — no sqlite_vec). Guards zero-norm: a zero-vector candidate gets
    similarity -inf so it sinks to the bottom. Tie-break is stable (preserves input order).
    Does not catch exceptions — the caller wraps this in try/except.
    """
    import math

    texts = [query, *candidates]
    vecs = embed_fn(texts)
    q_vec = vecs[0]
    cand_vecs = vecs[1:]

    q_norm = math.sqrt(sum(x * x for x in q_vec))

    sims: list[float] = []
    for vec in cand_vecs:
        c_norm = math.sqrt(sum(x * x for x in vec))
        if q_norm == 0.0 or c_norm == 0.0:
            sims.append(float("-inf"))
        else:
            dot = sum(a * b for a, b in zip(q_vec, vec, strict=False))
            sims.append(dot / (q_norm * c_norm))

    # Stable descending sort: equal sims keep input order (Python sort is stable).
    order = sorted(range(len(candidates)), key=lambda i: -sims[i])
    return [candidates[i] for i in order]


def _rgb_distractors(probe: dict, probes: list[dict], n: int, embed_fn=None) -> list[str]:
    """Return up to n distractor passages from other probes' gold fields. Never raises.

    Selection is deterministic: probes sorted by id, excluding self.
    A string gold contributes one passage; a list gold contributes each item individually.
    Probes with no gold field contribute nothing. Returns [] when no others have gold.

    When embed_fn is None (default): returns pool[:n] in id-order — byte-identical to the
    original behavior. When embed_fn is provided: reorders the pool topically-nearest-first
    via _rank_by_similarity; any exception falls back to id-order.
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
        if embed_fn is None:
            return passages[:n]
        try:
            ranked = _rank_by_similarity(probe["question"], passages, embed_fn)
            return ranked[:n]
        except Exception:
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
    embed_fn=None,
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
        distractors = _rgb_distractors(probe, probes, n=n_distractors, embed_fn=embed_fn)
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
    embed_fn=None,
) -> dict | None:
    """Negative rejection axis for one probe. Never raises.

    Context = k distractors ONLY (no gold). Correct == model declines to answer.
    Scored via _judge_rejection majority (fast-path regex first, then LLM judge).
    Returns a record dict or None on error.
    """
    try:
        distractors = _rgb_distractors(probe, probes, n=k, embed_fn=embed_fn)
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
    embed_fn=None,
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
        distractors = _rgb_distractors(probe, probes, n=n_distractors, embed_fn=embed_fn)
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
# RGB dispatcher
# ──────────────────────────────────────────────────────────────────────────────


def _run_rgb(args: argparse.Namespace, probes: list[dict]) -> int:
    """Dispatch the RGB four-axes evaluation. Never raises. Returns 0 on success.

    Sweeps noise_ratios for the noise axis; all other axes run once per probe.
    Emits JSON to args.out when provided; always prints a console summary table.
    Returns 1 only when every axis produced zero usable records.
    """
    try:
        axes = {a.strip() for a in args.axes.split(",") if a.strip()}
        noise_ratios = [float(r.strip()) for r in args.noise_ratios.split(",") if r.strip()]
        judge_models = [m.strip() for m in args.judge_models.split(",") if m.strip()]
        k = args.rgb_k

        # Build embed_fn when --hard-negatives is requested; soft-fail to id-order on error.
        embed_fn = None
        hard_negatives = False
        if getattr(args, "hard_negatives", False):
            try:
                embed_fn = _default_embedder(args.embed_model)
                hard_negatives = True
            except Exception as exc:
                print(f"note: hard-negatives unavailable, proceeding id-order (fastembed): {exc}")

        output: dict = {}

        # Noise axis: sweep ratios.
        if "noise" in axes:
            per_ratio: dict[str, dict] = {}
            per_probe_noise: list[dict] = []
            for ratio in noise_ratios:
                records = []
                for probe in probes:
                    rec = _rgb_noise(
                        probe, probes, ratio, k, args.answer_model, judge_models, embed_fn=embed_fn
                    )
                    if rec is not None:
                        records.append(rec)
                        per_probe_noise.append({**rec, "ratio": ratio})
                n = len(records)
                successes = sum(1 for r in records if r.get("majority"))
                accuracy = successes / n if n else 0.0
                low, high = _wilson(successes, n)
                per_ratio[str(ratio)] = {
                    "accuracy": accuracy,
                    "n": n,
                    "wilson_ci": [low, high],
                }
            output["noise"] = {"per_ratio": per_ratio, "per_probe": per_probe_noise}

        # Negative axis.
        if "negative" in axes:
            records = []
            for probe in probes:
                rec = _rgb_negative(
                    probe, probes, k, args.answer_model, judge_models, embed_fn=embed_fn
                )
                if rec is not None:
                    records.append(rec)
            n = len(records)
            rejections = sum(1 for r in records if r.get("rejected"))
            rejection_rate = rejections / n if n else 0.0
            low, high = _wilson(rejections, n)
            output["negative"] = {
                "rejection_rate": rejection_rate,
                "n": n,
                "wilson_ci": [low, high],
                "per_probe": records,
            }

        # Integration axis.
        if "integration" in axes:
            records = []
            skipped = 0
            for probe in probes:
                rec = _rgb_integration(
                    probe, probes, k, args.answer_model, judge_models, embed_fn=embed_fn
                )
                if rec is None:
                    skipped += 1
                    print(f"integration: skipped {probe.get('id')} (needs >=2 gold)")
                else:
                    records.append(rec)
            n = len(records)
            successes = sum(1 for r in records if r.get("majority"))
            accuracy = successes / n if n else 0.0
            low, high = _wilson(successes, n)
            output["integration"] = {
                "accuracy": accuracy,
                "n": n,
                "wilson_ci": [low, high],
                "skipped": skipped,
                "per_probe": records,
            }

        # Counterfactual axis.
        if "counterfactual" in axes:
            records = []
            skipped = 0
            for probe in probes:
                rec = _rgb_counterfactual(probe, args.answer_model, judge_models)
                if rec is None:
                    skipped += 1
                else:
                    records.append(rec)
            n = len(records)
            robust_count = sum(1 for r in records if r.get("robust"))
            misled_count = sum(1 for r in records if r.get("misled"))
            robust_rate = robust_count / n if n else 0.0
            misled_rate = misled_count / n if n else 0.0
            low, high = _wilson(robust_count, n)
            output["counterfactual"] = {
                "robust_rate": robust_rate,
                "misled_rate": misled_rate,
                "n": n,
                "wilson_ci": [low, high],
                "skipped": skipped,
                "per_probe": records,
            }

        output["hard_negatives"] = hard_negatives

        if args.out is not None:
            try:
                args.out.write_text(json.dumps(output, indent=2))
            except Exception as exc:
                print(f"warning: could not write results to {args.out}: {exc}")

        # Console summary table.
        print(f"\n{'axis':<16} {'metric':>12} {'wilson_ci':>20} {'n':>6}")
        print("-" * 58)
        if "noise" in output:
            for ratio_str, data in output["noise"]["per_ratio"].items():
                ci = f"[{data['wilson_ci'][0]:.3f}, {data['wilson_ci'][1]:.3f}]"
                print(
                    f"{'noise r=' + ratio_str:<16} {data['accuracy']:>12.3f} {ci:>20} {data['n']:>6}"
                )
        if "negative" in output:
            data = output["negative"]
            ci = f"[{data['wilson_ci'][0]:.3f}, {data['wilson_ci'][1]:.3f}]"
            print(f"{'negative':<16} {data['rejection_rate']:>12.3f} {ci:>20} {data['n']:>6}")
        if "integration" in output:
            data = output["integration"]
            ci = f"[{data['wilson_ci'][0]:.3f}, {data['wilson_ci'][1]:.3f}]"
            print(f"{'integration':<16} {data['accuracy']:>12.3f} {ci:>20} {data['n']:>6}")
        if "counterfactual" in output:
            data = output["counterfactual"]
            ci = f"[{data['wilson_ci'][0]:.3f}, {data['wilson_ci'][1]:.3f}]"
            robust_str = "r=" + f"{data['robust_rate']:.3f}"
            print(f"{'counterfactual':<16} {robust_str:>12} {ci:>20} {data['n']:>6}")

        # Return 1 only when every axis has zero records.
        all_empty = all(
            (
                "noise" not in output
                or all(v["n"] == 0 for v in output["noise"]["per_ratio"].values()),
                "negative" not in output or output["negative"]["n"] == 0,
                "integration" not in output or output["integration"]["n"] == 0,
                "counterfactual" not in output or output["counterfactual"]["n"] == 0,
            )
        )
        return 1 if all_empty else 0
    except Exception:
        return 1


# ──────────────────────────────────────────────────────────────────────────────
# PromptAB dispatcher
# ──────────────────────────────────────────────────────────────────────────────


def _read_variant(path: Path) -> str | None:
    """Read and strip an instruction-variant file. Never raises.

    Returns the stripped text on success, or None on any error (missing file, permission
    error, decode error, etc.).
    """
    try:
        return path.read_text().strip()
    except Exception:
        return None


def _run_promptab(args: argparse.Namespace, probes: list[dict]) -> int:
    """A/B-test two answer-instruction variants over a single fixed context arm. Never raises.

    Reads variant A and B instruction text from files (args.variant_a / args.variant_b),
    builds a context prefix via build_context_prefix for each probe, then evaluates both
    instruction variants using the same multi-judge majority idiom as the layers-mode arm
    loop.  Applies a Wilson-CI-gated decision rule: ADOPT_B only when B strictly beats A
    AND their Wilson CIs do not overlap, else NO_CHANGE.

    Returns 0 on success, 1 on guard failure (unreadable variant, retrieval arm, n==0).
    """
    try:
        # Read variant instruction files.
        a_text = _read_variant(args.variant_a) if args.variant_a is not None else None
        b_text = _read_variant(args.variant_b) if args.variant_b is not None else None
        if a_text is None:
            print(f"note: could not read variant-a file: {args.variant_a}")
            return 1
        if b_text is None:
            print(f"note: could not read variant-b file: {args.variant_b}")
            return 1

        # Guard: promptab supports only build_context_prefix arms (not retrieval arms).
        arm = args.layers[0]
        if arm in {"wikirag", "wikivec"}:
            print(
                f"note: promptab does not support retrieval arm '{arm}'; "
                "use a build_context_prefix arm (none, pack, memory, wiki, full)"
            )
            return 1

        judge_models = [m.strip() for m in args.judge_models.split(",") if m.strip()]

        # Accumulate successes and n for each variant.
        successes: dict[str, int] = {"a": 0, "b": 0}
        totals: dict[str, int] = {"a": 0, "b": 0}

        for label, text in (("a", a_text), ("b", b_text)):
            for _trial in range(args.trials):
                for probe in probes:
                    with MemoryStore(root=args.root) as mem:
                        prefix = build_context_prefix(
                            args.root,
                            mem,
                            query=probe["question"],
                            include_layers=_LAYERS_MAP[arm],
                        )
                    answer = _answer(prefix, probe["question"], args.answer_model, instruction=text)
                    if answer == "":
                        votes = [None] * len(judge_models)
                    else:
                        votes = [_factcheck(answer, probe["ground_truth"], m) for m in judge_models]
                    yes = sum(1 for v in votes if v is True)
                    majority = yes > len(judge_models) / 2
                    totals[label] += 1
                    if majority:
                        successes[label] += 1

        n_a = totals["a"]
        n_b = totals["b"]

        a_acc = successes["a"] / n_a if n_a else 0.0
        b_acc = successes["b"] / n_b if n_b else 0.0
        a_low, a_high = _wilson(successes["a"], n_a)
        b_low, b_high = _wilson(successes["b"], n_b)

        a_sha = hashlib.sha1(a_text.encode()).hexdigest()[:12]
        b_sha = hashlib.sha1(b_text.encode()).hexdigest()[:12]

        delta = round(b_acc - a_acc, 3)
        ci_overlap = not (b_low > a_high or a_low > b_high)
        decision = "ADOPT_B" if (b_acc > a_acc and not ci_overlap) else "NO_CHANGE"

        # JSON output (when --out is provided).
        output = {
            "mode": "promptab",
            "arm": arm,
            "trials": args.trials,
            "answer_model": args.answer_model,
            "judge_models": judge_models,
            "variant_a": {
                "accuracy": a_acc,
                "n": n_a,
                "wilson_ci": [a_low, a_high],
                "text_sha": a_sha,
            },
            "variant_b": {
                "accuracy": b_acc,
                "n": n_b,
                "wilson_ci": [b_low, b_high],
                "text_sha": b_sha,
            },
            "delta": delta,
            "ci_overlap": ci_overlap,
            "decision": decision,
        }

        if args.out is not None:
            try:
                args.out.write_text(json.dumps(output, indent=2))
            except Exception as exc:
                print(f"warning: could not write results to {args.out}: {exc}")

        # Console summary table.
        print(f"\n{'variant':<10} {'accuracy':>10} {'wilson_ci':>22} {'n':>6}")
        print("-" * 52)
        for label, acc, lo, hi, n in (
            ("a", a_acc, a_low, a_high, n_a),
            ("b", b_acc, b_low, b_high, n_b),
        ):
            ci = f"[{lo:.3f}, {hi:.3f}]"
            print(f"{label:<10} {acc:>10.3f} {ci:>22} {n:>6}")
        print(f"\ndelta={delta}  ci_overlap={ci_overlap}  decision={decision}")

        return 1 if (n_a == 0 and n_b == 0) else 0
    except Exception:
        return 1


# ──────────────────────────────────────────────────────────────────────────────
# SysAB helpers
# ──────────────────────────────────────────────────────────────────────────────

# Matches the first FIRST or SECOND token in a pairwise judge response.
_FIRSTSECOND_RE = re.compile(r"\b(FIRST|SECOND)\b", re.IGNORECASE)


def _generate_strategy(answers: InterviewAnswers, system_prompt: str, model: str) -> str:
    """Generate a strategy document for the given scenario and system prompt. Never raises.

    Single-shot bridge call with no tools and no canon injection — the goal is to isolate
    the system prompt's effect on generation quality. This deliberately deviates from
    StrategyAdapter which uses WebSearch + max_turns=5 and inject_canon=True. Here we want
    exactly one generation pass per prompt variant with zero external noise (no web search,
    no prior knowledge, no multi-turn), so any quality difference is attributable solely to
    the system prompt under test.

    Returns the stripped output text on success, or "" on any failure.
    """
    try:
        prompt = _build_pressure_test_prompt(answers)
        # inject_canon=False + max_turns=1 + no tools: isolate the system prompt's effect on
        # a single-shot generation. Deliberate deviation from StrategyAdapter's
        # WebSearch/max_turns=5 config — external signals would confound the A/B signal.
        bridge = ClaudeBridge(
            BridgeConfig(model=model, max_turns=1, allowed_tools=[], inject_canon=False)
        )
        br = bridge.run(prompt, system_prompt=system_prompt)
        return br.output.strip() if br.success and br.output.strip() else ""
    except Exception:
        return ""


def _judge_pairwise(
    scenario_question: str,
    doc_first: str,
    doc_second: str,
    model: str,
) -> str | None:
    """Pairwise rubric judge: which strategy doc is better? Never raises.

    Presents two strategy documents to a judge model and asks it to choose FIRST or SECOND.
    Uses the same subprocess idiom as _factcheck (not the bridge) for lightweight single
    invocations. Returns 'FIRST', 'SECOND', or None (unparseable / non-zero rc / no binary).

    Five-dimension rubric: problem clarity, 10x potential, feasibility realism,
    risk identification quality, recommendation decisiveness.
    """
    try:
        claude = _locate_claude()
        if claude is None:
            return None
        prompt = (
            "You are evaluating two strategy documents on five dimensions:\n"
            "1. Problem clarity\n"
            "2. 10x potential\n"
            "3. Feasibility realism\n"
            "4. Risk identification quality\n"
            "5. Recommendation decisiveness\n\n"
            f"Question: {scenario_question}\n\n"
            f"DOCUMENT FIRST:\n{doc_first}\n\n"
            f"DOCUMENT SECOND:\n{doc_second}\n\n"
            "Which document is better overall across these five dimensions? "
            "Reply with ONLY the word FIRST or SECOND."
        )
        cmd = [claude, "--print", "--max-turns", "1", "--model", model, "--", prompt]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=_JUDGE_TIMEOUT)
        if proc.returncode != 0:
            return None
        m = _FIRSTSECOND_RE.search(proc.stdout or "")
        if m is None:
            return None
        return m.group(1).upper()
    except Exception:
        return None


def _run_sysab(args: argparse.Namespace, probes: list[dict]) -> int:
    """A/B-test two strategy system prompts via pairwise generation + judgment. Never raises.

    For each scenario: generates a strategy document per variant (single-shot, no tools),
    judges them pairwise with position-debiasing (both orderings per judge model), and
    accumulates B-wins for a Wilson-CI-vs-0.5 decision gate.

    Variant A defaults to the live STRATEGY_SYSTEM_PROMPT when --variant-a is omitted.
    Returns 0 on success, 1 on guard failure (unreadable file, zero comparisons).
    """
    try:
        # Load scenarios (reuses _load_probes — same JSON-list-of-dicts contract).
        scenarios = _load_probes(args.scenarios)
        if scenarios is None:
            print(f"note: could not load scenarios from {args.scenarios}")
            return 1

        # Resolve variant A: file path takes precedence; absent → live constant.
        if args.variant_a is not None:
            a_text = _read_variant(args.variant_a)
            if a_text is None:
                print(f"note: could not read variant-a file: {args.variant_a}")
                return 1
        else:
            a_text = STRATEGY_SYSTEM_PROMPT

        # Variant B is always required.
        b_text = _read_variant(args.variant_b)
        if b_text is None:
            print(f"note: could not read variant-b file: {args.variant_b}")
            return 1

        judge_models = [m.strip() for m in args.judge_models.split(",") if m.strip()]

        comparisons = 0
        b_wins = 0

        for scenario in scenarios:
            answers = InterviewAnswers(
                core_problem=scenario.get("core_problem", ""),
                ten_x_vision=scenario.get("ten_x_vision", ""),
                milestones=scenario.get("milestones", []),
                architecture_pattern=scenario.get("architecture_pattern", ""),
                test_coverage=scenario.get("test_coverage", 80),
            )
            scenario_question = scenario.get("question") or scenario.get("core_problem", "")

            for _trial in range(args.trials):
                doc_a = _generate_strategy(answers, a_text, args.answer_model)
                doc_b = _generate_strategy(answers, b_text, args.answer_model)
                if not doc_a or not doc_b:
                    continue

                for judge_model in judge_models:
                    # Position-debiased: run BOTH orderings per (scenario, trial, judge).
                    # ordering1: first=doc_a, second=doc_b → "SECOND" = B-win.
                    # ordering2: first=doc_b, second=doc_a → "FIRST"  = B-win.
                    # None vote counts as a comparison but NOT a B-win (position bias unknown).
                    vote1 = _judge_pairwise(scenario_question, doc_a, doc_b, judge_model)
                    comparisons += 1
                    if vote1 == "SECOND":
                        b_wins += 1

                    vote2 = _judge_pairwise(scenario_question, doc_b, doc_a, judge_model)
                    comparisons += 1
                    if vote2 == "FIRST":
                        b_wins += 1

        n = comparisons
        b_win_rate = b_wins / n if n else 0.0
        low, high = _wilson(b_wins, n)
        decision = "ADOPT_B" if (b_win_rate > 0.5 and low > 0.5) else "NO_CHANGE"

        def text_sha(text: str) -> str:
            return hashlib.sha1(text.encode()).hexdigest()[:12]

        output = {
            "mode": "sysab",
            "adapter": "strategy",
            "n_scenarios": len(scenarios),
            "trials": args.trials,
            "answer_model": args.answer_model,
            "judge_models": judge_models,
            "variant_a": {
                "text_sha": text_sha(a_text),
                "is_default_prompt": args.variant_a is None,
            },
            "variant_b": {
                "text_sha": text_sha(b_text),
            },
            "comparisons": n,
            "b_wins": b_wins,
            "b_win_rate": b_win_rate,
            "wilson_ci": [low, high],
            "decision": decision,
        }

        if args.out is not None:
            try:
                args.out.write_text(json.dumps(output, indent=2))
            except Exception as exc:
                print(f"warning: could not write results to {args.out}: {exc}")

        # Console summary (mirrors _run_promptab visual style).
        print(f"\n{'sysab':<16} {'b_win_rate':>12} {'wilson_ci':>22} {'comparisons':>12}")
        print("-" * 64)
        ci = f"[{low:.3f}, {high:.3f}]"
        print(f"{'strategy':<16} {b_win_rate:>12.3f} {ci:>22} {n:>12}")
        print(f"\ndecision={decision}")

        return 1 if n == 0 else 0
    except Exception:
        return 1


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
    # RGB flags (additive — ignored when --mode layers).
    parser.add_argument("--mode", choices=("layers", "rgb", "promptab", "sysab"), default="layers")
    parser.add_argument("--axes", default="noise,negative,integration,counterfactual")
    parser.add_argument("--noise-ratios", default="0.0,0.4,0.8")
    parser.add_argument("--rgb-k", type=int, default=5)
    parser.add_argument(
        "--hard-negatives",
        action="store_true",
        help=(
            "Reorder RGB distractors topically-nearest-first via the existing embedder "
            "(--embed-model). Soft-fails to id-order when fastembed is unavailable. "
            "RGB-mode only."
        ),
    )
    # PromptAB flags (additive — ignored when --mode is not promptab).
    parser.add_argument(
        "--variant-a",
        type=Path,
        default=None,
        help="Path to a text file containing the Variant A answer instruction.",
    )
    parser.add_argument(
        "--variant-b",
        type=Path,
        default=None,
        help="Path to a text file containing the Variant B answer instruction.",
    )
    # SysAB flag (additive — ignored when --mode is not sysab).
    parser.add_argument(
        "--scenarios",
        type=Path,
        default=None,
        help=(
            "JSON list of strategy scenarios for --mode sysab. sysab reads its input here; "
            "--probes stays required by the parser but is ignored by sysab "
            "(pass any probes file to satisfy it)."
        ),
    )
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

        # RGB mode: dispatch to _run_rgb and return immediately; arm loop does not run.
        if args.mode == "rgb":
            return _run_rgb(args, probes)

        # PromptAB mode: dispatch to _run_promptab and return immediately.
        if args.mode == "promptab":
            return _run_promptab(args, probes)

        # SysAB mode: dispatch to _run_sysab and return immediately.
        if args.mode == "sysab":
            return _run_sysab(args, probes)

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
