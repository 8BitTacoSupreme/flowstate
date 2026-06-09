"""Synthetic-project scaffold + deterministic between-run mutation.

``scaffold(root)`` writes a self-consistent FlowState target under ``root``:
  - .planning/fixtures/starter.json   (via generate_starter_fixture)
  - flowstate.json                    (FlowStateModel + a small install_manifest)
  - .planning/phases/01-foundation/01-VERIFICATION.md  (frontmatter + Gaps bullets)
  - coverage.xml                      (Cobertura line-rate BELOW the fixture gate)
  - a seeded baseline RUN journal entry so run 0 has a prior to diff against

It resets to a PRISTINE baseline on every call: ``memory.db`` and every generated
pipeline output (PROJECT.md, ROADMAP.md, config.json, GOTCHAS.md, RUNLOG.md,
research/, .claude/, .mcp.json) are removed first, so a scaffold never inherits
stale on-disk state from a prior run. This is what makes the harness reproducible.

The fixture/VERIFICATION content is byte-stable across scaffolds; ``flowstate.json``
carries fresh timestamps (``created_at`` / ``updated_at``) and is therefore NOT
byte-stable — only the deterministic artifacts are.

``mutate_for_run(root, i)`` applies a deterministic, index-keyed change that
models a project converging across runs. Same ``i`` always produces the same
result. It drives REAL signal on all four axes under cheap-dry:
  - convergence: rewrites a shrinking subset of manifest-tracked artifacts AND
    recomputes their checksums, so the journal's artifacts_changed delta shrinks.
  - verify: raises coverage.xml's line-rate from below the gate to above it, so
    the verify axis transitions fail -> pass across runs.
  - gotcha-learning / enrichment: resolves one Gaps bullet per run so the harvest
    surfaces fewer NEW gotchas while memory accumulates.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import shutil
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

# Several manifest-tracked artifacts; mutate_for_run rewrites a SHRINKING subset
# of them each run so the journal's artifacts_changed delta trends down.
_ARTIFACT_COUNT = 4
_ARTIFACT_REL_TMPL = ".planning/artifacts/work_{n}.txt"

# Coverage trajectory: starts BELOW the fixture's 80% gate (fail) and climbs to
# meet it (pass), so the verify axis genuinely flips fail -> pass over the runs.
_COVERAGE_GATE_PCT = 80
_COVERAGE_START_PCT = 60

# Generated pipeline outputs cleared on every scaffold so the baseline is pristine.
_GENERATED_FILES: tuple[str, ...] = (
    "memory.db",
    ".mcp.json",
    ".planning/PROJECT.md",
    ".planning/ROADMAP.md",
    ".planning/config.json",
    ".planning/GOTCHAS.md",
    ".planning/RUNLOG.md",
)
_GENERATED_DIRS: tuple[str, ...] = (
    "research",
    ".claude",
)

# A distinct run_id for the seeded baseline RUN entry. Because append_run_entry is
# idempotent per run_id, this never collides with the pipeline's own run_ids and
# gives run 0 a non-empty prior snapshot to diff against (so convergence can fall).
_BASELINE_RUN_ID = "bench-baseline"


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


def _artifact_rel(n: int) -> str:
    return _ARTIFACT_REL_TMPL.format(n=n)


def _checksum(body: str) -> str:
    return hashlib.sha256(body.encode()).hexdigest()[:16]


def _converged_body(n: int) -> str:
    """The stable, final body of artifact ``n`` once it has converged."""
    return f"foundation work artifact {n}\n"


def _coverage_xml(rate: float) -> str:
    """A minimal Cobertura coverage report carrying just the root line-rate."""
    return (
        '<?xml version="1.0" ?>\n'
        f'<coverage line-rate="{rate:.4f}" version="bench">\n'
        "  <packages/>\n"
        "</coverage>\n"
    )


def _write_coverage(root: Path, pct: float) -> None:
    (root / "coverage.xml").write_text(_coverage_xml(pct / 100.0))


def _clean_generated(root: Path) -> None:
    """Remove all generated pipeline output so the baseline is pristine. Never raises."""
    for rel in _GENERATED_FILES:
        with contextlib.suppress(Exception):
            (root / rel).unlink(missing_ok=True)
    for rel in _GENERATED_DIRS:
        with contextlib.suppress(Exception):
            shutil.rmtree(root / rel, ignore_errors=True)
    # Drop any artifacts dir so stale work_*.txt from a prior run cannot leak in.
    with contextlib.suppress(Exception):
        shutil.rmtree(root / ".planning" / "artifacts", ignore_errors=True)


def _seed_baseline_run(root: Path, manifest: list[InstallEntry]) -> None:
    """Seed a baseline RUN journal entry so run 0 has a full-churn prior to diff.

    The baseline snapshot deliberately records DIFFERENT checksums for every
    tracked artifact, so the first real run's diff sees the maximum delta and the
    convergence axis can then fall. Never raises.
    """
    from flowstate.memory import MemoryEntry, MemoryKind, MemoryStore

    snapshot = {
        e.path: "0" * 16  # a checksum no real body will ever produce
        for e in manifest
        if e.checksum is not None
    }
    store = MemoryStore(root=root)
    try:
        store.add(
            MemoryEntry.create(
                MemoryKind.RUN,
                content=f"baseline {_BASELINE_RUN_ID}",
                summary=f"run {_BASELINE_RUN_ID} — baseline",
                metadata={"snapshot": snapshot, "artifacts_changed": []},
                run_id=_BASELINE_RUN_ID,
            )
        )
    finally:
        with contextlib.suppress(Exception):
            store.close()


def scaffold(root: Path) -> None:
    """Create / refresh the synthetic target under ``root`` as a PRISTINE baseline.

    Clears memory.db and every generated pipeline output first, so each call
    starts from the committed baseline only (reproducible run-to-run).
    """
    root = Path(root)
    _clean_generated(root)

    planning = root / ".planning"
    (planning / "fixtures").mkdir(parents=True, exist_ok=True)

    # ── Fixture (drives verify gates + the ## Eval Fixtures prefix layer) ─────
    fixture = generate_starter_fixture(_interview(), project_name="bench-sample")
    fixture_path = planning / "fixtures" / "starter.json"
    fixture_path.write_text(json.dumps(fixture, indent=2, sort_keys=True) + "\n")

    # ── Manifest-tracked artifacts (checksummed; convergence reads their delta) ──
    manifest: list[InstallEntry] = []
    artifacts_dir = root / ".planning" / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    for n in range(_ARTIFACT_COUNT):
        body = _converged_body(n)
        (root / _artifact_rel(n)).write_text(body)
        manifest.append(
            InstallEntry(
                path=_artifact_rel(n),
                owner="bench",
                kind="artifact",
                checksum=_checksum(body),
            )
        )
    manifest.append(
        InstallEntry(
            path=".planning/fixtures/starter.json",
            owner="bench",
            kind="fixture",
            checksum=None,
        )
    )

    # ── coverage.xml BELOW the gate so the verify axis starts failing ────────
    _write_coverage(root, _COVERAGE_START_PCT)

    # ── VERIFICATION.md with a Gaps section (feeds harvest_planning_gotchas) ──
    _write_verification(root, _GAPS)

    # ── flowstate.json with the install_manifest ─────────────────────────────
    state = FlowStateModel()
    state.preferences.dry_run = True
    state.preferences.project_name = "bench-sample"
    state.interview = _interview()
    state.install_manifest = manifest
    save_state(state, root)

    # ── Seed a baseline RUN entry so run 0 already has a prior snapshot ───────
    _seed_baseline_run(root, manifest)


def _coverage_pct_for_run(i: int) -> float:
    """Climb coverage from the start pct toward (and past) the gate across runs."""
    # +10 pts per run; clamped so it lands at/above the gate and stays there.
    pct = _COVERAGE_START_PCT + 10 * max(0, i)
    return float(min(100, pct))


def mutate_for_run(root: Path, i: int) -> None:
    """Apply the deterministic mutation for run index ``i``. Same ``i`` is stable.

    Drives real movement on all four axes (see module docstring):
      - resolves the first ``i`` gaps so fewer NEW gotchas surface over runs;
      - rewrites a SHRINKING subset of manifest artifacts (and recomputes their
        checksums in flowstate.json) so the journal's artifacts_changed delta
        falls toward zero — real convergence signal;
      - raises coverage.xml above the gate so verify flips fail -> pass.
    """
    from flowstate.state import load_state

    root = Path(root)
    remaining = max(0, len(_GAPS) - max(0, i))
    gaps = _GAPS[len(_GAPS) - remaining :] if remaining else ()
    _write_verification(root, gaps)

    # Coverage climbs across runs so the verify gate transitions fail -> pass.
    _write_coverage(root, _coverage_pct_for_run(i))

    # Rewrite a shrinking subset of artifacts: the first ``remaining`` of them get
    # a run-varying body (churn), the rest sit at their converged body. Fewer
    # artifacts churn as gaps resolve, so the journal delta shrinks across runs.
    state = load_state(root)
    manifest_by_path = {e.path: e for e in state.install_manifest}
    for n in range(_ARTIFACT_COUNT):
        rel = _artifact_rel(n)
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        # Active artifacts (index < remaining) carry a run-varying churn line; the
        # rest sit at their converged body. Fewer churn as gaps resolve.
        body = _converged_body(n) + (f"churn run {i}\n" if n < remaining else "")
        path.write_text(body)
        entry = manifest_by_path.get(rel)
        if entry is not None:
            entry.checksum = _checksum(body)
    save_state(state, root)
