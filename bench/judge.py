"""Tier-2 LLM-as-judge — does FlowState's accumulating context improve OUTPUT quality?

The mechanical scorecard proves context *accumulates* (prefix grows, churn converges,
gotchas dedupe). It cannot tell whether the richer context makes the produced work
*better*. This judge scores each run's LLM-produced artifacts (research report +
strategy) against the fixture's ``system_contract`` + ``retrieval_questions``, so a
RISING score across runs is evidence that accumulated context improved output quality.

Decoupling: it calls the ``claude`` CLI directly via subprocess — NOT
``flowstate.bridge`` — so bench stays independent of the LLM substrate, mirroring how
FlowState locates/invokes claude. Never raises: any failure yields a ``None`` score
(reported as insufficient-data) and NEVER affects the mechanical CompoundingScore.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

_JUDGE_TIMEOUT = 180
# LLM-produced artifacts worth judging (PROJECT.md/ROADMAP.md are deterministic templates).
_ARTIFACT_FILES = ("research/report.md", "research/strategy.md", "research/brief.md")
_MAX_ARTIFACT_CHARS = 8000
_SCORE_RE = re.compile(r'\{[^{}]*"score"[^{}]*\}', re.DOTALL)


@dataclass(frozen=True)
class JudgeResult:
    run_index: int
    score: float | None  # 0-10; None = could not judge (insufficient-data)
    rationale: str


def _locate_claude() -> str | None:
    """Locate the claude CLI (stdlib only; no flowstate.bridge import). Never raises."""
    try:
        env = os.environ.get("FLOWSTATE_CLAUDE_BIN")
        if env and Path(env).is_file():
            return env
        found = shutil.which("claude")
        if found:
            return found
        for c in (
            Path.home() / ".local" / "bin" / "claude",
            Path("/usr/local/bin/claude"),
            Path("/opt/homebrew/bin/claude"),
        ):
            if c.is_file():
                return str(c)
    except Exception:
        return None
    return None


def collect_artifacts(root: Path) -> str:
    """Concatenate the run's LLM-produced artifacts (truncated). Never raises."""
    parts: list[str] = []
    for rel in _ARTIFACT_FILES:
        p = root / rel
        try:
            if p.is_file():
                txt = p.read_text(errors="ignore").strip()
                if txt:
                    parts.append(f"### {rel}\n{txt}")
        except Exception:
            continue
    return "\n\n".join(parts)[:_MAX_ARTIFACT_CHARS]


def _build_prompt(fixture: dict, artifacts: str) -> str:
    contract = str(fixture.get("system_contract", ""))
    questions = "\n".join(f"- {x}" for x in (fixture.get("retrieval_questions") or []))
    gates = "\n".join(f"- {x}" for x in (fixture.get("acceptance_gates") or []))
    return (
        "You score the QUALITY of planning artifacts a tool produced for a software "
        "project. Be a strict grader.\n\n"
        f"SYSTEM CONTRACT (what the work must honor):\n{contract}\n\n"
        f"RUBRIC — the artifacts should concretely address these questions:\n{questions}\n\n"
        f"ACCEPTANCE GATES:\n{gates}\n\n"
        f"PRODUCED ARTIFACTS:\n{artifacts or '(none produced)'}\n\n"
        "Reward grounded, specific, non-generic content that addresses the contract and "
        "rubric; penalize vagueness, boilerplate, hedging, and contradiction. Output ONLY "
        'a JSON object: {"score": <integer 0-10>, "rationale": "<one sentence>"}.'
    )


def _parse_score(out: str) -> tuple[float | None, str]:
    for m in reversed(_SCORE_RE.findall(out or "")):
        try:
            d = json.loads(m)
        except Exception:
            continue
        s = d.get("score")
        if isinstance(s, (int, float)) and not isinstance(s, bool):
            return float(s), str(d.get("rationale", ""))[:200]
    return None, ""


def judge_run(
    run_index: int, artifacts: str, fixture: dict, *, model: str | None = None
) -> JudgeResult:
    """Score one run's artifacts via ``claude --print``. Never raises."""
    claude = _locate_claude()
    if not claude or not artifacts.strip():
        return JudgeResult(run_index, None, "no judge bridge or no artifacts")
    cmd = [claude, "--print", "--max-turns", "1"]
    if model:
        cmd += ["--model", model]
    cmd += ["--", _build_prompt(fixture, artifacts)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=_JUDGE_TIMEOUT)
        score, rationale = _parse_score(proc.stdout)
        return JudgeResult(run_index, score, rationale or "(no rationale parsed)")
    except Exception as exc:
        return JudgeResult(run_index, None, f"judge error: {exc}")


def summarize(results: list[JudgeResult]) -> dict:
    """Trend over the per-run scores. Excluded from the mechanical CompoundingScore.

    trend: improving | flat | declining | insufficient-data (needs >=2 real scores).
    """
    scored = [r for r in results if r.score is not None]
    if len(scored) < 2:
        return {
            "scores": [r.score for r in results],
            "trend": "insufficient-data",
            "first": scored[0].score if scored else None,
            "last": scored[-1].score if scored else None,
            "delta": None,
        }
    first, last = scored[0].score, scored[-1].score
    delta = round(last - first, 2)
    trend = "improving" if delta > 0.5 else "declining" if delta < -0.5 else "flat"
    return {
        "scores": [r.score for r in results],
        "trend": trend,
        "first": first,
        "last": last,
        "delta": delta,
    }
