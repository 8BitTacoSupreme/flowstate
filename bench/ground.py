"""bench/ground.py — one-time auto-derived repo grounding for the real-mode verdict.

The Phase-22 real-repo path scaffolds a copy of the subject repo but never grounds
the pipeline in it: pointed at a raw repo, ``load_state`` returns an empty interview,
so every arm plans a generic/empty project and research discards every section. This
module closes that gap.

``ground_from_repo(root)`` derives an ``InterviewAnswers`` from the subject repo via
ONE bounded ``claude --print`` call (README + a cheap structural summary in, STRICT
JSON out), writes it into ``root/flowstate.json``, then runs the repomix pack so the
``pack``/``full`` arms carry real repo content. It is a ONE-TIME setup gate — the
derivation LLM call must NOT run per-trial (it would vary across arms and confound the
paired design). Called once on ``--root`` before the sweep, its output is frozen into
``flowstate.json`` and every ``_worktree`` copy inherits it via ``scaffold(synthetic=False)``.

This is NOT the unrelated ``bench/grounding.py`` (the RGB/promptab retrieval benchmark).

Fails LOUD: malformed derivation JSON or an absent repomix binary raises RuntimeError
rather than writing garbage state or silently continuing.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from flowstate.bridge import BridgeConfig, ClaudeBridge
from flowstate.pack import _find_repomix, run_pack
from flowstate.state import InterviewAnswers, load_state, save_state

# Bound the untrusted repo text that enters the derivation prompt (T-22gf-02):
# a slice of README + a shallow structural summary, never a full-tree crawl.
_README_MAX_BYTES = 8 * 1024
_PACK_MAX_BYTES = 8 * 1024
_STRUCT_MAX_ENTRIES = 60
_STRUCT_MAX_FILES_PER_DIR = 12

# Source-file suffixes worth naming in the structural summary.
_SOURCE_SUFFIXES = frozenset(
    {".py", ".js", ".ts", ".tsx", ".go", ".rs", ".java", ".rb", ".md", ".toml", ".yaml", ".yml"}
)

_REPOMIX_PACK_REL = ".planning/codebase/repomix-pack.xml"


def _read_readme(root: Path) -> str:
    """Return a bounded slice of ``root/README.md`` (tolerate absence)."""
    for name in ("README.md", "README.rst", "README.txt", "README"):
        p = root / name
        if p.is_file():
            try:
                return p.read_text(errors="replace")[:_README_MAX_BYTES]
            except OSError:
                return ""
    return ""


def _structural_summary(root: Path) -> str:
    """Build a cheap, bounded structural summary of the repo.

    Prefers an existing repomix pack slice; otherwise a shallow one-level walk of
    top-level dirs naming a bounded set of source files. No full-tree crawl.
    """
    pack = root / _REPOMIX_PACK_REL
    if pack.is_file():
        try:
            return "Repomix pack (excerpt):\n" + pack.read_text(errors="replace")[:_PACK_MAX_BYTES]
        except OSError:
            pass

    lines: list[str] = ["Top-level structure:"]
    entries = 0
    try:
        top = sorted(root.iterdir(), key=lambda p: p.name)
    except OSError:
        return "\n".join(lines)

    for entry in top:
        if entries >= _STRUCT_MAX_ENTRIES:
            break
        if entry.name.startswith("."):
            continue
        if entry.is_dir():
            lines.append(f"- {entry.name}/")
            entries += 1
            files = 0
            try:
                children = sorted(entry.iterdir(), key=lambda p: p.name)
            except OSError:
                continue
            for child in children:
                if files >= _STRUCT_MAX_FILES_PER_DIR or entries >= _STRUCT_MAX_ENTRIES:
                    break
                if child.is_file() and child.suffix in _SOURCE_SUFFIXES:
                    lines.append(f"    - {child.name}")
                    files += 1
                    entries += 1
        elif entry.suffix in _SOURCE_SUFFIXES:
            lines.append(f"- {entry.name}")
            entries += 1
    return "\n".join(lines)


def _derivation_prompt(readme: str, structure: str) -> str:
    """Compose the STRICT-JSON derivation prompt from bounded repo context."""
    return (
        "You are grounding a project-planning pipeline in an existing code repository.\n"
        "From the README and structural summary below, infer the project's context.\n\n"
        "Respond with STRICT JSON only — no prose, no markdown fences — an object with "
        "exactly these keys:\n"
        '  "core_problem": string (the problem the project solves),\n'
        '  "ten_x_vision": string (the ambitious end-state),\n'
        '  "architecture_pattern": string (the dominant architectural pattern),\n'
        '  "milestones": array of short strings (3-5 near-term milestones),\n'
        '  "research_focus": string (comma-separated technical topics worth researching).\n\n'
        f"README:\n{readme or '(no README found)'}\n\n"
        f"{structure}\n\n"
        "Output ONLY the JSON object."
    )


def ground_from_repo(root: Path) -> InterviewAnswers:
    """Derive + persist an interview for ``root`` and run the repomix pack.

    ONE bounded ``claude --print`` json-mode call derives the interview from the
    repo's README + structural summary; the parsed fields are written into
    ``root/flowstate.json`` and a repomix pack is produced. Idempotent per ``root``
    (safe to re-run). Fails LOUD (RuntimeError) on malformed derivation JSON, a
    failed bridge call, or an absent repomix binary.

    Returns the derived ``InterviewAnswers`` (also persisted to state).
    """
    root = Path(root)
    readme = _read_readme(root)
    structure = _structural_summary(root)
    prompt = _derivation_prompt(readme, structure)

    bridge = ClaudeBridge(BridgeConfig(project_root=root))
    br = bridge.run(
        prompt,
        allowed_tools=[],
        max_turns=2,
        model="sonnet",
        output_format="json",
    )
    if not br.success:
        raise RuntimeError(f"repo-grounding derivation call failed: {br.error or 'unknown error'}")

    try:
        parsed = json.loads(br.output)
        if not isinstance(parsed, dict):
            raise ValueError("derivation JSON was not an object")
    except (json.JSONDecodeError, ValueError) as exc:
        raise RuntimeError(f"repo-grounding derivation returned unparseable JSON: {exc}") from exc

    milestones = parsed.get("milestones", [])
    if not isinstance(milestones, list):
        milestones = []
    interview = InterviewAnswers(
        research_focus=str(parsed.get("research_focus", "") or ""),
        core_problem=str(parsed.get("core_problem", "") or ""),
        ten_x_vision=str(parsed.get("ten_x_vision", "") or ""),
        milestones=[str(m) for m in milestones],
        architecture_pattern=str(parsed.get("architecture_pattern", "") or ""),
    )

    state = load_state(root)
    state.interview = interview
    save_state(state, root)

    # Guard repomix BEFORE packing so an absent binary fails loud with the install
    # hint rather than a downstream pack-arm carrying no repo content (T-22gf-04).
    if not _find_repomix():
        raise RuntimeError(
            "repomix CLI not found. Install repomix or set "
            "FLOWSTATE_REPOMIX_BIN to the binary path."
        )
    result = run_pack(root)
    if not result.success:
        raise RuntimeError(f"repomix pack failed during grounding: {result.error}")

    return interview


def main(argv: list[str] | None = None) -> int:
    """CLI entry: ``python -m bench.ground --root <repo>``. Exit 0 on success."""
    ap = argparse.ArgumentParser(
        prog="bench.ground",
        description="One-time auto-derive repo grounding (interview + repomix pack).",
    )
    ap.add_argument("--root", type=Path, required=True)
    args = ap.parse_args(argv)

    try:
        interview = ground_from_repo(args.root)
    except RuntimeError as exc:
        print(f"[ground] failed: {exc}", file=sys.stderr)
        return 1
    print(f"[ground] grounded {args.root} (research_focus: {interview.research_focus!r})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
