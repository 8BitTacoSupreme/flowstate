"""Manual prompt-tuning loop for bench — LAB TOOL ONLY.

This module mines probe failures of a live answer-instruction, proposes ONE candidate
instruction via a single ``claude --print`` call, gates the candidate through
``bench.grounding._run_promptab``, and emits a human-approval report (.json + .md).

HARD STOP: This tool does not modify any source files. Apply manually after human review.

There is no ``--apply`` flag. The loop never edits any file under ``flowstate/`` or any
adapter, and it never auto-applies a candidate instruction. The human reads the emitted
report and makes the one change by hand.

Usage::

    python -m bench.tune_loop \\
        --root /path/to/project \\
        --probes bench/fixtures/grounding_probes.example.json \\
        --arm none

Output: ``./.tune_runs/<timestamp>/tune_report.md`` (+ tune_report.json).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import types
from datetime import UTC, datetime
from pathlib import Path

from bench.grounding import (
    _LAYERS_MAP,
    MemoryStore,
    _answer,
    _factcheck,
    _load_probes,
    _read_variant,
    _run_promptab,
    build_context_prefix,
)
from bench.judge import _locate_claude

# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────

_CANDIDATE_TIMEOUT = 120
_DEFAULT_BASELINE = Path("bench/fixtures/instr_baseline.txt")

_DISCLAIMER = "This tool does not modify any source files. Apply manually after human review."


# ──────────────────────────────────────────────────────────────────────────────
# Core functions
# ──────────────────────────────────────────────────────────────────────────────


def _mine_failures(
    root: Path,
    probes: list[dict],
    base_instruction: str,
    arm: str,
    answer_model: str,
    judge_models: list[str],
) -> list[dict]:
    """Run each probe against base_instruction; return failing probe records.

    A probe is a FAILURE when the majority of judges say the answer is wrong (or
    when the answer is empty — counts as all-None votes, i.e., zero yes-count).

    Returns a list of failure dicts with keys: id, question, ground_truth, answer.
    Never raises — returns [] on any unhandled error.
    """
    try:
        failures: list[dict] = []
        for probe in probes:
            with MemoryStore(root=root) as mem:
                prefix = build_context_prefix(
                    root,
                    mem,
                    query=probe["question"],
                    include_layers=_LAYERS_MAP[arm],
                )
            answer = _answer(prefix, probe["question"], answer_model, instruction=base_instruction)
            if answer == "":
                votes: list[bool | None] = [None] * len(judge_models)
            else:
                votes = [_factcheck(answer, probe["ground_truth"], m) for m in judge_models]
            yes_count = sum(1 for v in votes if v is True)
            majority = yes_count > len(judge_models) / 2
            if not majority:
                failures.append(
                    {
                        "id": probe["id"],
                        "question": probe["question"],
                        "ground_truth": probe["ground_truth"],
                        "answer": answer,
                    }
                )
        return failures
    except Exception:
        return []


def _propose_candidate(
    base_instruction: str,
    failures: list[dict],
    model: str,
) -> str | None:
    """Propose ONE improved answer instruction via a single ``claude --print`` call.

    Empty failures list -> returns None immediately (no subprocess call).
    Returns the stripped stdout if rc==0 and non-empty, else None.
    Never raises — returns None on any unhandled error.
    """
    try:
        if not failures:
            return None
        claude = _locate_claude()
        if claude is None:
            return None
        failure_lines = "\n".join(
            f"- Question: {f['question']}\n"
            f"  Correct answer: {f['ground_truth']}\n"
            f"  Model answered: {f['answer']}"
            for f in failures
        )
        prompt = (
            "You are tuning an answer instruction used in a factual QA benchmark.\n\n"
            f"CURRENT INSTRUCTION:\n{base_instruction}\n\n"
            f"The instruction FAILED on these probe cases:\n{failure_lines}\n\n"
            "Propose a single improved answer instruction that is more likely to produce "
            "accurate, specific answers for these cases. "
            "OUTPUT ONLY the new instruction text — no preamble, no markdown, no explanation."
        )
        cmd = [claude, "--print", "--max-turns", "1", "--model", model, "--", prompt]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=_CANDIDATE_TIMEOUT)
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout.strip()
        return None
    except Exception:
        return None


def _gate(
    root: Path,
    probes: list[dict],
    base_text: str,
    candidate_text: str,
    arm: str,
    answer_model: str,
    judge_models: str,
    trials: int,
    work_dir: Path,
) -> dict | None:
    """Gate the candidate instruction through _run_promptab; return the verdict dict.

    Writes base_text -> work_dir/base_instruction.txt and
    candidate_text -> work_dir/candidate_instruction.txt, then calls _run_promptab
    via a SimpleNamespace with the exact attributes it expects.

    The judge_models parameter is passed as the raw COMMA STRING to the SimpleNamespace
    (because _run_promptab splits it internally).

    Returns the parsed gate.json dict on success, or None on any failure.
    Never raises.
    """
    try:
        base_path = work_dir / "base_instruction.txt"
        candidate_path = work_dir / "candidate_instruction.txt"
        gate_path = work_dir / "gate.json"
        base_path.write_text(base_text)
        candidate_path.write_text(candidate_text)

        ns = types.SimpleNamespace(
            variant_a=base_path,
            variant_b=candidate_path,
            layers=[arm],
            judge_models=judge_models,  # raw comma STRING — _run_promptab splits it
            trials=trials,
            answer_model=answer_model,
            root=root,
            out=gate_path,
        )
        _run_promptab(ns, probes)

        if not gate_path.exists():
            return None
        try:
            return json.loads(gate_path.read_text())
        except Exception:
            return None
    except Exception:
        return None


def _emit_report(
    work_dir: Path,
    base_text: str,
    candidate_text: str,
    failures: list[dict],
    gate: dict | None,
    arm: str,
) -> Path:
    """Emit tune_report.json and tune_report.md into work_dir.

    The .md always includes the exact disclaimer:
      "This tool does not modify any source files. Apply manually after human review."

    Returns the path to tune_report.md (best-effort; never raises).
    """
    try:

        def _sha(text: str) -> str:
            return hashlib.sha1(text.encode()).hexdigest()[:12]

        decision = gate["decision"] if gate else "NO_CANDIDATE"
        failure_ids = [f["id"] for f in failures]

        report_json: dict = {
            "arm": arm,
            "n_failures": len(failures),
            "failure_ids": failure_ids,
            "base_sha": _sha(base_text),
            "candidate_sha": _sha(candidate_text),
            "gate": gate,
            "decision": decision,
            "candidate_instruction": candidate_text,
        }
        json_path = work_dir / "tune_report.json"
        json_path.write_text(json.dumps(report_json, indent=2))

        # ── Markdown report ──────────────────────────────────────────────────
        md_lines: list[str] = []
        md_lines.append("# Tune Loop Report\n")
        md_lines.append(f"> {_DISCLAIMER}\n")
        md_lines.append("---\n")

        # Summary section
        md_lines.append("## Summary\n")
        md_lines.append(f"- **Decision:** {decision}")
        md_lines.append(f"- **Failures mined:** {len(failures)}")
        md_lines.append(f"- **Arm:** {arm}")
        if gate:
            va = gate.get("variant_a", {})
            vb = gate.get("variant_b", {})
            ci_a = va.get("wilson_ci", [0, 0])
            ci_b = vb.get("wilson_ci", [0, 0])
            md_lines.append(
                f"- **Variant A accuracy:** {va.get('accuracy', 'n/a'):.3f}"
                f"  CI [{ci_a[0]:.3f}, {ci_a[1]:.3f}]"
            )
            md_lines.append(
                f"- **Variant B accuracy:** {vb.get('accuracy', 'n/a'):.3f}"
                f"  CI [{ci_b[0]:.3f}, {ci_b[1]:.3f}]"
            )
            md_lines.append(f"- **Delta:** {gate.get('delta', 'n/a')}")
            md_lines.append(f"- **CI overlap:** {gate.get('ci_overlap', 'n/a')}")
        md_lines.append("")

        # Candidate instruction
        md_lines.append("## Candidate Instruction\n")
        md_lines.append("```")
        md_lines.append(candidate_text if candidate_text else "(none)")
        md_lines.append("```\n")

        # Mined failures
        md_lines.append("## Mined Failures\n")
        if failures:
            for f in failures:
                md_lines.append(f"- **{f['id']}**: {f['question']}")
        else:
            md_lines.append("- (none)")
        md_lines.append("")

        # Suggested action
        md_lines.append("## Suggested Action\n")
        if decision == "ADOPT_B":
            md_lines.append(
                "The candidate instruction beats the baseline with non-overlapping Wilson CIs. "
                "To adopt it, manually replace the answer instruction "
                "(e.g. the default in flowstate or the relevant adapter prompt) "
                "with the candidate above after your own review."
            )
        else:
            md_lines.append(
                "No change is warranted — the candidate did not demonstrate a statistically "
                "significant improvement over the baseline (or no candidate was proposed)."
            )
        md_lines.append("")
        md_lines.append(f"---\n\n_{_DISCLAIMER}_\n")

        md_path = work_dir / "tune_report.md"
        md_path.write_text("\n".join(md_lines))
        return md_path
    except Exception:
        # Best-effort: return the expected path even if write failed
        return work_dir / "tune_report.md"


# ──────────────────────────────────────────────────────────────────────────────
# Orchestrator
# ──────────────────────────────────────────────────────────────────────────────


def run_tune_loop(args: types.SimpleNamespace) -> int:
    """Run the full prompt-tuning loop. Never raises — returns 1 on any unhandled error.

    args attributes expected:
      root (Path), probes (Path), base_instruction (Path | None),
      arm (str), answer_model (str), judge_models (str — comma-separated),
      trials (int), out_dir (Path).

    Returns 0 on success (even when no candidate is found), 1 on fatal error.
    """
    try:
        probes = _load_probes(args.probes)
        if probes is None:
            print(f"note: could not load probes from {args.probes}")
            return 1

        base_path = (
            args.base_instruction if args.base_instruction is not None else _DEFAULT_BASELINE
        )
        base = _read_variant(base_path)
        if base is None:
            print(f"note: could not read base instruction from {base_path}")
            return 1

        out_dir: Path = args.out_dir
        out_dir.mkdir(parents=True, exist_ok=True)

        judge_list = [m.strip() for m in args.judge_models.split(",") if m.strip()]

        failures = _mine_failures(args.root, probes, base, args.arm, args.answer_model, judge_list)

        if not failures:
            print("note: no failures found — emitting NO_CANDIDATE report")
            report = _emit_report(out_dir, base, "", [], None, args.arm)
            print(f"report: {report}")
            return 0

        candidate = _propose_candidate(base, failures, args.answer_model)
        if candidate is None:
            print("note: could not propose candidate — emitting NO_CANDIDATE report")
            report = _emit_report(out_dir, base, "", failures, None, args.arm)
            print(f"report: {report}")
            return 0

        # Pass raw comma STRING to _gate (it forwards to SimpleNamespace for _run_promptab)
        gate = _gate(
            args.root,
            probes,
            base,
            candidate,
            args.arm,
            args.answer_model,
            args.judge_models,
            args.trials,
            out_dir,
        )

        report = _emit_report(out_dir, base, candidate, failures, gate, args.arm)
        decision = gate["decision"] if gate else "NO_CANDIDATE"
        print(f"decision: {decision}")
        print(f"report: {report}")
        return 0
    except Exception:
        return 1


# ──────────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    """Build and return the argument parser for bench.tune_loop."""
    parser = argparse.ArgumentParser(
        prog="bench.tune_loop",
        description=(
            "Manual prompt-tuning loop. "
            "Mines failures, proposes a candidate instruction, gates it, "
            "emits a human-approval report. "
            f"{_DISCLAIMER}"
        ),
    )
    parser.add_argument(
        "--root",
        type=Path,
        required=True,
        help="Project root (used by MemoryStore and build_context_prefix).",
    )
    parser.add_argument(
        "--probes",
        type=Path,
        required=True,
        help="Path to the grounding probes JSON file.",
    )
    parser.add_argument(
        "--base-instruction",
        type=Path,
        default=None,
        help=(f"Path to the base answer-instruction file (default: {_DEFAULT_BASELINE})."),
    )
    parser.add_argument(
        "--arm",
        choices=list(_LAYERS_MAP.keys()),
        default="none",
        help="Context arm to use when building the prefix (default: none).",
    )
    parser.add_argument(
        "--answer-model",
        default="sonnet",
        help="Model used for answering and candidate proposal (default: sonnet).",
    )
    parser.add_argument(
        "--judge-models",
        default="sonnet,sonnet,opus",
        help="Comma-separated judge model list (default: sonnet,sonnet,opus).",
    )
    parser.add_argument(
        "--trials",
        type=int,
        default=2,
        help="Number of trials per variant in the _run_promptab gate (default: 2).",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help=(
            "Output directory for the report (default: ./.tune_runs/<timestamp>). "
            "The directory is created automatically."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point for bench.tune_loop. Never raises — returns rc from run_tune_loop."""
    try:
        parser = _build_parser()
        args = parser.parse_args(argv)
        if args.out_dir is None:
            ts = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
            args.out_dir = Path(".tune_runs") / ts
        return run_tune_loop(args)
    except SystemExit as exc:
        return int(exc.code) if exc.code is not None else 1
    except Exception:
        return 1


if __name__ == "__main__":
    sys.exit(main())
