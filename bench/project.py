"""Synthetic-project scaffold + deterministic between-run mutation.

``scaffold(root)`` writes a self-consistent FlowState target under ``root``:
  - .planning/fixtures/starter.json   (via generate_starter_fixture)
  - flowstate.json                    (FlowStateModel + a small install_manifest)
  - .planning/phases/01-foundation/01-VERIFICATION.md  (frontmatter + Gaps bullets)

It is idempotent: re-running overwrites in place with byte-stable content.

``mutate_for_run(root, i)`` applies a deterministic, index-keyed change that
models a project converging across runs — artifact deltas shrink and one gap is
resolved per run. Same ``i`` always produces the same result.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from flowstate.context import generate_starter_fixture
from flowstate.state import FlowStateModel, InstallEntry, InterviewAnswers, save_state

# The full set of gaps the scaffold starts with. mutate_for_run removes the
# first ``i`` of these (clamped) so later runs surface fewer outstanding gaps.
_GAPS: tuple[str, ...] = (
    "missing error handling on the ingest path",
    "no input validation on the public endpoint",
    "verify coverage gate not yet wired",
    "race condition in the worker pool",
)

_PHASE_DIR = ".planning/phases/01-foundation"
_VERIFICATION_NAME = "01-VERIFICATION.md"
_ARTIFACT_REL = ".planning/artifacts/work.txt"


def _interview() -> InterviewAnswers:
    """Stable interview answers for the synthetic target (no randomness)."""
    return InterviewAnswers(
        research_focus="compounding measurement apparatus",
        core_problem="prove run N+1 beats run N on the same project",
        ten_x_vision="each run starts smarter than the last",
        milestones=["Foundation", "Compounding loop"],
        test_coverage=80,
        architecture_pattern="event-driven orchestrator",
        deployment_target="cli",
    )


def _verification_text(gaps: tuple[str, ...]) -> str:
    """Render a VERIFICATION.md with frontmatter status and a Gaps bullet list."""
    lines = [
        "---",
        "status: drafted",
        "phase: 01-foundation",
        "---",
        "",
        "# Phase 01 Foundation — Verification",
        "",
        "## Gaps",
        "",
    ]
    for gap in gaps:
        lines.append(f"- {gap}")
    lines.append("")
    return "\n".join(lines)


def _write_verification(root: Path, gaps: tuple[str, ...]) -> None:
    phase_dir = root / _PHASE_DIR
    phase_dir.mkdir(parents=True, exist_ok=True)
    (phase_dir / _VERIFICATION_NAME).write_text(_verification_text(gaps))


def scaffold(root: Path) -> None:
    """Create / refresh the synthetic target under ``root``. Idempotent."""
    root = Path(root)
    planning = root / ".planning"
    (planning / "fixtures").mkdir(parents=True, exist_ok=True)

    # ── Fixture (drives verify gates + the ## Eval Fixtures prefix layer) ─────
    fixture = generate_starter_fixture(_interview(), project_name="bench-sample")
    fixture_path = planning / "fixtures" / "starter.json"
    fixture_path.write_text(json.dumps(fixture, indent=2, sort_keys=True) + "\n")

    # ── A real artifact the install_manifest can point at (checksummed) ──────
    artifact_path = root / _ARTIFACT_REL
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_body = "foundation work artifact\n"
    artifact_path.write_text(artifact_body)
    checksum = hashlib.sha256(artifact_body.encode()).hexdigest()[:16]

    # ── VERIFICATION.md with a Gaps section (feeds harvest_planning_gotchas) ──
    _write_verification(root, _GAPS)

    # ── flowstate.json with a small valid install_manifest ───────────────────
    state = FlowStateModel()
    state.preferences.dry_run = True
    state.preferences.project_name = "bench-sample"
    state.interview = _interview()
    state.install_manifest = [
        InstallEntry(
            path=_ARTIFACT_REL,
            owner="bench",
            kind="artifact",
            checksum=checksum,
        ),
        InstallEntry(
            path=".planning/fixtures/starter.json",
            owner="bench",
            kind="fixture",
            checksum=None,
        ),
    ]
    save_state(state, root)


def mutate_for_run(root: Path, i: int) -> None:
    """Apply the deterministic mutation for run index ``i``. Same ``i`` is stable.

    Resolves the first ``i`` gaps (clamped) so successive runs surface fewer
    outstanding gaps — modeling a project that improves because prior findings
    were available. Artifact deltas shrink accordingly.
    """
    root = Path(root)
    remaining = max(0, len(_GAPS) - max(0, i))
    gaps = _GAPS[len(_GAPS) - remaining :] if remaining else ()
    _write_verification(root, gaps)

    # Shrink the artifact body deterministically so checksum churn decreases as
    # gaps resolve (fewer remaining gaps => more stable artifact).
    artifact_path = root / _ARTIFACT_REL
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    body = "foundation work artifact\n" + ("pending\n" * remaining)
    artifact_path.write_text(body)
