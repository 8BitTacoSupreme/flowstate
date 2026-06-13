"""Tests for the bench/ intrinsic compounding harness.

Covers (built incrementally across the Phase A tasks):
  - metric-core: each axis fires on a compounding sequence, detects regression
    on a worsening sequence, K=1 insufficient-data, never-raises on empty/short.
  - capture: _LAYER_HEADINGS coupling to context_prefix.py, never-raises reads,
    scaffold idempotency, gotcha attribution.
  - runner/report: caveat present, table+panel render, judge-stub refusal.
  - e2e: cheap-seed 3-iteration axes fire, cheap-dry smoke, JSON determinism.
"""

from __future__ import annotations

from pathlib import Path

from bench.metrics import (
    RunSnapshot,
    Scorecard,
    axis_convergence,
    axis_enrichment,
    axis_gotcha_learning,
    axis_verify_non_regression,
    compute_scorecard,
)

# ── Metric-core helpers ─────────────────────────────────────────────────────


def _snap(
    i: int,
    *,
    artifacts_changed: int = 0,
    new_gotchas: int = 0,
    reencountered_gotchas: int = 0,
    verify_pass: int = 0,
    verify_fail: int = 0,
    verify_skip: int = 0,
    prefix_tokens: int = 0,
    mem_hits: int = 0,
    layers_present: tuple[str, ...] = (),
) -> RunSnapshot:
    return RunSnapshot(
        run_index=i,
        run_id=f"run{i}",
        artifacts_changed=artifacts_changed,
        new_gotchas=new_gotchas,
        reencountered_gotchas=reencountered_gotchas,
        verify_pass=verify_pass,
        verify_fail=verify_fail,
        verify_skip=verify_skip,
        prefix_tokens=prefix_tokens,
        mem_hits=mem_hits,
        layers_present=layers_present,
    )


def _compounding_sequence() -> list[RunSnapshot]:
    """A hand-built sequence where every axis registers compounding."""
    return [
        _snap(
            0,
            artifacts_changed=8,
            new_gotchas=4,
            reencountered_gotchas=0,
            verify_pass=2,
            verify_fail=2,
            prefix_tokens=100,
            mem_hits=1,
            layers_present=("## Eval Fixtures",),
        ),
        _snap(
            1,
            artifacts_changed=5,
            new_gotchas=2,
            reencountered_gotchas=2,
            verify_pass=3,
            verify_fail=1,
            prefix_tokens=200,
            mem_hits=3,
            layers_present=("## Eval Fixtures", "## Gotchas"),
        ),
        _snap(
            2,
            artifacts_changed=2,
            new_gotchas=0,
            reencountered_gotchas=3,
            verify_pass=4,
            verify_fail=0,
            prefix_tokens=350,
            mem_hits=6,
            layers_present=("## Eval Fixtures", "## Gotchas", "## Prior Knowledge"),
        ),
    ]


def _regressing_sequence() -> list[RunSnapshot]:
    """A hand-built sequence where every axis registers regression."""
    return [
        _snap(
            0,
            artifacts_changed=2,
            new_gotchas=0,
            reencountered_gotchas=3,
            verify_pass=4,
            verify_fail=0,
            prefix_tokens=350,
            mem_hits=6,
            layers_present=("## Eval Fixtures", "## Gotchas", "## Prior Knowledge"),
        ),
        _snap(
            1,
            artifacts_changed=5,
            new_gotchas=2,
            reencountered_gotchas=2,
            verify_pass=3,
            verify_fail=1,
            prefix_tokens=200,
            mem_hits=3,
            layers_present=("## Eval Fixtures", "## Gotchas"),
        ),
        _snap(
            2,
            artifacts_changed=8,
            new_gotchas=4,
            reencountered_gotchas=0,
            verify_pass=2,
            verify_fail=2,
            prefix_tokens=100,
            mem_hits=1,
            layers_present=("## Eval Fixtures",),
        ),
    ]


# ── Axis unit tests ─────────────────────────────────────────────────────────


def test_axis_convergence_fires_on_decreasing_deltas():
    assert axis_convergence(_compounding_sequence()) == "compounding"


def test_axis_convergence_detects_regression_on_rising_deltas():
    assert axis_convergence(_regressing_sequence()) == "regressing"


def test_axis_gotcha_learning_fires_when_new_decays():
    assert axis_gotcha_learning(_compounding_sequence()) == "compounding"


def test_axis_gotcha_learning_detects_regression_when_new_rises():
    assert axis_gotcha_learning(_regressing_sequence()) == "regressing"


def test_axis_verify_non_regression_fires_when_improving():
    assert axis_verify_non_regression(_compounding_sequence()) == "compounding"


def test_axis_verify_non_regression_detects_regression():
    assert axis_verify_non_regression(_regressing_sequence()) == "regressing"


def test_axis_enrichment_fires_when_prefix_grows():
    assert axis_enrichment(_compounding_sequence()) == "compounding"


def test_axis_enrichment_detects_regression_when_prefix_shrinks():
    assert axis_enrichment(_regressing_sequence()) == "regressing"


def test_flat_sequence_yields_flat_on_every_axis():
    flat = [
        _snap(0, artifacts_changed=4, new_gotchas=1, verify_pass=3, prefix_tokens=200, mem_hits=2),
        _snap(1, artifacts_changed=4, new_gotchas=1, verify_pass=3, prefix_tokens=200, mem_hits=2),
    ]
    assert axis_convergence(flat) == "flat"
    assert axis_gotcha_learning(flat) == "flat"
    assert axis_verify_non_regression(flat) == "flat"
    assert axis_enrichment(flat) == "flat"


# ── Scorecard tests ─────────────────────────────────────────────────────────


def test_compute_scorecard_compounding_verdict():
    card = compute_scorecard(_compounding_sequence())
    assert isinstance(card, Scorecard)
    assert card.compounding_score >= 2
    assert card.axis_enrichment == "compounding"
    assert "regressing" not in (
        card.axis_convergence,
        card.axis_gotcha_learning,
        card.axis_verify_non_regression,
        card.axis_enrichment,
    )
    assert card.verdict == "compounding"


def test_compute_scorecard_score_clamped_and_in_range():
    card = compute_scorecard(_regressing_sequence())
    assert -4 <= card.compounding_score <= 4
    assert card.verdict != "compounding"


def test_k1_yields_all_flat_insufficient_data_and_score_zero():
    card = compute_scorecard([_snap(0, artifacts_changed=3, prefix_tokens=100)])
    assert card.axis_convergence == "flat"
    assert card.axis_gotcha_learning == "flat"
    assert card.axis_verify_non_regression == "flat"
    assert card.axis_enrichment == "flat"
    assert card.compounding_score == 0
    assert card.verdict != "compounding"


def test_compute_scorecard_never_raises_on_empty_and_single():
    # empty list
    card_empty = compute_scorecard([])
    assert card_empty.compounding_score == 0
    assert card_empty.verdict != "compounding"
    # single snapshot
    card_single = compute_scorecard([_snap(0)])
    assert card_single.compounding_score == 0


def test_axes_never_raise_on_empty_input():
    for fn in (
        axis_convergence,
        axis_gotcha_learning,
        axis_verify_non_regression,
        axis_enrichment,
    ):
        assert fn([]) == "flat"
        assert fn([_snap(0)]) == "flat"


def test_verdict_requires_enrichment_compounding():
    """Score >= 2 but enrichment flat must NOT yield a compounding verdict."""
    seq = [
        _snap(
            0,
            artifacts_changed=8,
            new_gotchas=4,
            verify_pass=2,
            verify_fail=2,
            prefix_tokens=200,
            mem_hits=3,
        ),
        _snap(
            1,
            artifacts_changed=2,
            new_gotchas=0,
            reencountered_gotchas=3,
            verify_pass=4,
            verify_fail=0,
            prefix_tokens=200,
            mem_hits=3,
        ),
    ]
    card = compute_scorecard(seq)
    assert card.axis_enrichment == "flat"
    assert card.verdict != "compounding"


_FIXTURE_ROOT = Path(__file__).resolve().parent.parent / "bench" / "fixtures" / "sample_project"


# ── Task 2: capture + project ───────────────────────────────────────────────


def test_layer_headings_match_context_prefix_source():
    """_LAYER_HEADINGS must match the actual headings emitted by context_prefix.py.

    Fails loudly if any heading drifts in the source module.
    """
    from bench.capture import _LAYER_HEADINGS

    flowstate_dir = Path(__file__).resolve().parent.parent / "flowstate"
    # "## Prior Knowledge" is emitted by MemoryStore.get_context (memory.py),
    # the other three by context_prefix.py. Scan the union of the emitters so
    # the guard couples to wherever each heading actually originates.
    src = (
        (flowstate_dir / "context_prefix.py").read_text()
        + "\n"
        + (flowstate_dir / "memory.py").read_text()
    )
    expected = (
        "## Eval Fixtures",
        "## Gotchas",
        "## Prior Knowledge",
        "## Since Last Run",
    )
    assert expected == _LAYER_HEADINGS
    for heading in _LAYER_HEADINGS:
        assert heading in src, f"layer heading drifted from its emitter: {heading!r}"


def test_capture_run_snapshot_never_raises_on_empty_dir(tmp_path: Path):
    from bench.capture import capture_run_snapshot
    from bench.metrics import RunSnapshot

    snap = capture_run_snapshot(tmp_path, "anything")
    assert isinstance(snap, RunSnapshot)
    assert snap.run_index == 0
    # Empty dir degrades to zeros / empty layers.
    assert snap.artifacts_changed == 0
    assert snap.layers_present == ()


def test_capture_run_index_derives_from_prior(tmp_path: Path):
    from bench.capture import capture_run_snapshot

    first = capture_run_snapshot(tmp_path, "q")
    second = capture_run_snapshot(tmp_path, "q", prior=first)
    assert second.run_index == first.run_index + 1


def test_scaffold_is_idempotent(tmp_path: Path):
    from bench.project import scaffold

    scaffold(tmp_path)
    fixture = tmp_path / ".planning" / "fixtures" / "starter.json"
    state = tmp_path / "flowstate.json"
    verification = tmp_path / ".planning" / "phases" / "01-foundation" / "01-VERIFICATION.md"
    assert fixture.exists()
    assert state.exists()
    assert verification.exists()
    first_fixture = fixture.read_text()
    first_verification = verification.read_text()

    scaffold(tmp_path)  # second run
    assert fixture.read_text() == first_fixture
    assert verification.read_text() == first_verification


def test_scaffold_verification_has_gaps_section(tmp_path: Path):
    from bench.project import scaffold

    scaffold(tmp_path)
    verification = (
        tmp_path / ".planning" / "phases" / "01-foundation" / "01-VERIFICATION.md"
    ).read_text()
    assert "Gaps" in verification
    # harvest_planning_gotchas should find bullets to capture.
    assert "- " in verification


def test_scaffold_verification_feeds_harvest(tmp_path: Path):
    """The scaffolded VERIFICATION.md must produce gotchas via harvest_planning_gotchas."""
    from bench.project import scaffold
    from flowstate.gotchas import harvest_planning_gotchas
    from flowstate.memory import MemoryStore

    scaffold(tmp_path)
    store = MemoryStore(root=tmp_path)
    try:
        harvest_planning_gotchas(store, tmp_path)
        assert len(store.get_gotchas()) >= 1
    finally:
        store.close()


def test_scaffold_real_path_preserves_kickoff(tmp_path: Path):
    """scaffold(root, synthetic=False) preserves a real-style kickoff and removes memory.db."""
    import json

    from bench.project import scaffold

    # Build a real-style .planning tree.
    planning = tmp_path / ".planning"
    (planning / "fixtures").mkdir(parents=True, exist_ok=True)
    (planning / "codebase").mkdir(parents=True, exist_ok=True)

    config = {"context_prefix_budget_tokens": 40000}
    (planning / "config.json").write_text(json.dumps(config))

    starter_sentinel = {"sentinel": "real-kickoff", "retrieval_questions": []}
    (planning / "fixtures" / "starter.json").write_text(json.dumps(starter_sentinel))

    (planning / "codebase" / "repomix-pack.xml").write_text("<repomix/>")
    (planning / "PROJECT.md").write_text("# Real Project\n")
    (planning / "ROADMAP.md").write_text("# Real Roadmap\n")

    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)
    (claude_dir / "CLAUDE.md").write_text("# CLAUDE\n")

    research_dir = tmp_path / "research"
    research_dir.mkdir(parents=True, exist_ok=True)
    (research_dir / "brief.md").write_text("# Research Brief\n")

    (tmp_path / "memory.db").write_bytes(b"fake-db")

    scaffold(tmp_path, synthetic=False)

    # All kickoff artifacts must survive untouched.
    assert (planning / "config.json").exists()
    assert json.loads((planning / "config.json").read_text()) == config
    assert json.loads((planning / "fixtures" / "starter.json").read_text()) == starter_sentinel
    assert (planning / "codebase" / "repomix-pack.xml").read_text() == "<repomix/>"
    assert (planning / "PROJECT.md").read_text() == "# Real Project\n"
    assert (planning / "ROADMAP.md").read_text() == "# Real Roadmap\n"
    assert (claude_dir / "CLAUDE.md").read_text() == "# CLAUDE\n"
    assert (research_dir / "brief.md").read_text() == "# Research Brief\n"

    # memory.db must be deleted.
    assert not (tmp_path / "memory.db").exists()

    # No synthetic _converged_body artifacts must be written.
    assert not (tmp_path / ".planning" / "artifacts" / "work_0.txt").exists()


def test_scaffold_real_path_preserves_budget_key(tmp_path: Path):
    """After scaffold(root, synthetic=False), config.json still parses and has context_prefix_budget_tokens."""
    import json

    from bench.project import scaffold

    planning = tmp_path / ".planning"
    planning.mkdir(parents=True, exist_ok=True)
    (planning / "fixtures").mkdir(parents=True, exist_ok=True)

    config = {"context_prefix_budget_tokens": 40000, "extra_key": "preserved"}
    (planning / "config.json").write_text(json.dumps(config))
    (planning / "fixtures" / "starter.json").write_text("{}")

    scaffold(tmp_path, synthetic=False)

    parsed = json.loads((planning / "config.json").read_text())
    assert "context_prefix_budget_tokens" in parsed
    assert parsed["context_prefix_budget_tokens"] == 40000


def test_scaffold_synthetic_still_clears_and_writes(tmp_path: Path):
    """scaffold(root) / scaffold(root, synthetic=True) clears config.json and writes bench-sample artifacts."""
    import json

    from bench.project import scaffold

    # Pre-existing config.json must be cleared by synthetic scaffold.
    planning = tmp_path / ".planning"
    planning.mkdir(parents=True, exist_ok=True)
    (planning / "config.json").write_text(json.dumps({"context_prefix_budget_tokens": 99999}))

    scaffold(tmp_path)  # default: synthetic=True

    # Synthetic run must clear config.json (it's in _GENERATED_FILES).
    assert not (planning / "config.json").exists()

    # Synthetic bench-sample starter.json must be written.
    fixture_path = planning / "fixtures" / "starter.json"
    assert fixture_path.exists()
    fixture = json.loads(fixture_path.read_text())
    # generate_starter_fixture always includes system_contract and retrieval_questions.
    assert "system_contract" in fixture or "retrieval_questions" in fixture

    # _converged_body artifacts must be written.
    assert (tmp_path / ".planning" / "artifacts" / "work_0.txt").exists()


def test_mutate_for_run_is_deterministic(tmp_path: Path):
    from bench.project import mutate_for_run, scaffold

    scaffold(tmp_path)
    mutate_for_run(tmp_path, 1)
    snapshot_a = (
        tmp_path / ".planning" / "phases" / "01-foundation" / "01-VERIFICATION.md"
    ).read_text()

    # Re-scaffold + same mutation index yields identical content.
    scaffold(tmp_path)
    mutate_for_run(tmp_path, 1)
    snapshot_b = (
        tmp_path / ".planning" / "phases" / "01-foundation" / "01-VERIFICATION.md"
    ).read_text()
    assert snapshot_a == snapshot_b


def test_mutate_for_run_resolves_gaps_over_runs(tmp_path: Path):
    """Successive run indices remove gaps (gotcha gaps resolve over runs)."""
    from bench.project import mutate_for_run, scaffold

    scaffold(tmp_path)
    vpath = tmp_path / ".planning" / "phases" / "01-foundation" / "01-VERIFICATION.md"

    def _gap_count() -> int:
        return vpath.read_text().count("\n- ")

    mutate_for_run(tmp_path, 0)
    early = _gap_count()
    mutate_for_run(tmp_path, 2)
    late = _gap_count()
    assert late < early


def test_capture_attributes_new_gotchas_by_run_id(tmp_path: Path):
    """A gotcha stamped with the current run_id counts as new this run."""
    from datetime import UTC, datetime

    from bench.capture import capture_run_snapshot
    from flowstate.gotchas import capture_gotcha
    from flowstate.memory import MemoryStore

    store = MemoryStore(root=tmp_path)
    try:
        capture_gotcha(
            store,
            source="verifier",
            message="boom in foo.py",
            root=tmp_path,
            run_id="run0",
            timestamp=datetime.now(UTC),
        )
    finally:
        store.close()

    snap = capture_run_snapshot(tmp_path, "boom", run_id="run0")
    assert snap.new_gotchas >= 1


# ── Task 3: runner + report ─────────────────────────────────────────────────


def _captured_console_output(render) -> str:
    from io import StringIO

    from rich.console import Console

    buf = StringIO()
    console = Console(file=buf, width=120, force_terminal=False)
    render(console)
    return buf.getvalue()


def test_render_report_prints_caveat_and_renders():
    from bench.report import CAVEAT, render_report

    card = compute_scorecard(_compounding_sequence())
    out = _captured_console_output(lambda c: render_report(card, console=c))
    # The honest caveat must be present (allowing Rich to wrap it).
    assert "validates the apparatus" in out or "validates that the substrate" in out
    assert "Scorecard" in out
    # The caveat constant must name the causation distinction explicitly.
    assert "causes the llm to compound" in CAVEAT.lower()
    assert "regression guard" in out or "regression" in out


def test_render_report_markdown_branch():
    from bench.report import render_report

    card = compute_scorecard(_compounding_sequence())
    out = _captured_console_output(lambda c: render_report(card, console=c, markdown=True))
    assert "Compounding Eval Run" in out


def test_judge_stub_refuses_without_real_and_allow():
    import argparse
    from io import StringIO

    from rich.console import Console

    from bench.compound_eval import _judge_allowed

    buf = StringIO()
    console = Console(file=buf, width=120, force_terminal=False)
    # --judge in cheap mode without --allow-llm must refuse, not judge.
    args = argparse.Namespace(judge=True, mode="cheap", allow_llm=False)
    assert _judge_allowed(args, console) is False
    assert "requires --mode real AND --allow-llm" in buf.getvalue()


def test_judge_stub_noop_when_flag_absent():
    import argparse
    from io import StringIO

    from rich.console import Console

    from bench.compound_eval import _judge_allowed

    buf = StringIO()
    console = Console(file=buf, width=120, force_terminal=False)
    args = argparse.Namespace(judge=False, mode="cheap", allow_llm=False)
    assert _judge_allowed(args, console) is False
    assert buf.getvalue() == ""


# ── Task 4: sample_project fixture + cheap-seed e2e + cheap-dry smoke ────────


def _seed_run_entry(store, *, run_id: str, artifacts_changed: int) -> None:
    """Seed a MemoryKind.RUN journal entry with a given artifacts_changed count."""
    from flowstate.memory import MemoryEntry, MemoryKind

    store.add(
        MemoryEntry.create(
            MemoryKind.RUN,
            content=f"run {run_id} journal",
            summary=f"run {run_id}",
            metadata={"artifacts_changed": ["f"] * artifacts_changed},
            run_id=run_id,
        )
    )


def _seed_memory(store, *, run_id: str, n: int) -> None:
    """Seed N searchable RESEARCH memories so mem_hits / prefix grow across runs."""
    from flowstate.memory import MemoryEntry, MemoryKind

    for k in range(n):
        store.add(
            MemoryEntry.create(
                MemoryKind.RESEARCH,
                content=f"compounding finding {run_id}-{k} about vision architecture",
                summary=f"finding {run_id}-{k}",
                tags=["compounding"],
                run_id=run_id,
            )
        )


def test_cheap_seed_three_iteration_axes_fire(tmp_path: Path):
    """Deterministically seed a 3-run compounding trend and assert axes fire."""
    from bench.capture import capture_run_snapshot
    from bench.metrics import compute_scorecard
    from bench.project import scaffold
    from flowstate.gotchas import capture_gotcha
    from flowstate.memory import MemoryStore

    scaffold(tmp_path)
    probe = "compounding vision architecture"
    snapshots = []
    prior = None
    # Decreasing artifact deltas, decaying new gotchas, growing memory.
    plan = [
        {"run_id": "seedrun0", "artifacts": 8, "new_gotchas": 3, "mem": 1},
        {"run_id": "seedrun1", "artifacts": 4, "new_gotchas": 1, "mem": 3},
        {"run_id": "seedrun2", "artifacts": 1, "new_gotchas": 0, "mem": 6},
    ]
    for step in plan:
        store = MemoryStore(root=tmp_path)
        try:
            _seed_run_entry(store, run_id=step["run_id"], artifacts_changed=step["artifacts"])
            _seed_memory(store, run_id=step["run_id"], n=step["mem"])
            for g in range(step["new_gotchas"]):
                capture_gotcha(
                    store,
                    source="seed",
                    message=f"distinct gotcha {step['run_id']}-{g}",
                    root=tmp_path,
                    run_id=step["run_id"],
                )
        finally:
            store.close()
        snap = capture_run_snapshot(tmp_path, probe, prior=prior, run_id=step["run_id"])
        snapshots.append(snap)
        prior = snap

    card = compute_scorecard(snapshots)
    # Convergence: artifacts_changed 8 -> 1 decreasing.
    assert card.axis_convergence == "compounding"
    # Gotcha-learning: new gotchas 3 -> 0 decaying.
    assert card.axis_gotcha_learning == "compounding"
    # Enrichment: prefix tokens + mem hits grow as memory accumulates.
    assert card.axis_enrichment == "compounding"


def _dir_fingerprint(root: Path) -> dict[str, bytes]:
    """Map every file under ``root`` to its bytes — for byte-for-byte comparison."""
    return {
        str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()
    }


def test_cheap_dry_smoke_on_fixture_copy(tmp_path: Path):
    """Copy the checked-in sample_project and run the runner main() — never raises."""
    import shutil

    from bench.compound_eval import main

    dest = tmp_path / "sample_project"
    shutil.copytree(_FIXTURE_ROOT, dest)
    rc = main(["--mode", "cheap", "--runs", "2", "--root", str(dest)])
    assert rc == 0
    # The checked-in copy must be untouched by the run (we mutated only the copy).
    assert _FIXTURE_ROOT.exists()


def test_runner_leaves_source_root_byte_for_byte_unchanged():
    """Running main() directly against the checked-in fixture must not write to it.

    Strong assertion (LOW-01): snapshot every file's bytes before and after, and
    assert nothing changed and no pipeline output (PROJECT.md, memory.db, etc.)
    appeared in the source root. The runner copies --root into a temp dir, so the
    source fixture stays pristine even when --root IS the fixture.
    """
    from bench.compound_eval import main

    before = _dir_fingerprint(_FIXTURE_ROOT)
    rc = main(["--mode", "cheap", "--runs", "2", "--root", str(_FIXTURE_ROOT)])
    assert rc == 0
    after = _dir_fingerprint(_FIXTURE_ROOT)
    assert after == before, "runner mutated the checked-in source fixture"
    # Pipeline outputs must NOT appear in the source root.
    for leaked in (".planning/PROJECT.md", ".planning/ROADMAP.md", "memory.db", ".mcp.json"):
        assert not (_FIXTURE_ROOT / leaked).exists(), f"runner leaked {leaked} into source root"


def test_cheap_dry_smoke_writes_deterministic_json(tmp_path: Path):
    """main() with --out writes JSON; two write_json calls are byte-identical."""
    import shutil

    from bench.compound_eval import main
    from bench.metrics import compute_scorecard
    from bench.report import write_json

    dest = tmp_path / "sample_project"
    shutil.copytree(_FIXTURE_ROOT, dest)
    out = tmp_path / "results.json"
    rc = main(["--mode", "cheap", "--runs", "2", "--root", str(dest), "--out", str(out)])
    assert rc == 0
    assert out.exists()

    # JSON determinism: same scorecard -> byte-identical output.
    card = compute_scorecard(_compounding_sequence())
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    write_json(card, a)
    write_json(card, b)
    assert a.read_bytes() == b.read_bytes()


def test_sample_project_fixture_is_self_consistent():
    """The checked-in fixture exists with the three required files."""
    assert (_FIXTURE_ROOT / "flowstate.json").exists()
    assert (_FIXTURE_ROOT / ".planning" / "fixtures" / "starter.json").exists()
    assert (
        _FIXTURE_ROOT / ".planning" / "phases" / "01-foundation" / "01-VERIFICATION.md"
    ).exists()


# ── Review fixes: insufficient-data, verdict masking, --out, real-mode, axes ──


def test_axis_convergence_insufficient_data_when_artifacts_all_zero():
    """All-zero artifacts_changed => no convergence signal => insufficient-data, not flat."""
    seq = [_snap(0, artifacts_changed=0), _snap(1, artifacts_changed=0)]
    assert axis_convergence(seq) == "insufficient-data"


def test_axis_verify_insufficient_data_when_all_skip():
    """Verify all-skip every run (no pass/fail) => insufficient-data, not flat."""
    seq = [_snap(0, verify_skip=7), _snap(1, verify_skip=7)]
    assert axis_verify_non_regression(seq) == "insufficient-data"


def test_insufficient_data_does_not_count_toward_score():
    """An insufficient-data axis counts as neither compounding nor regressing.

    Here convergence has no signal (all-zero artifacts) while gotcha + enrichment
    compound. The score reflects only the two real compounding axes (=2), and the
    inert convergence axis neither inflates nor deflates it.
    """
    seq = [
        _snap(0, new_gotchas=4, prefix_tokens=100, mem_hits=1),
        _snap(1, new_gotchas=0, prefix_tokens=300, mem_hits=4),
    ]
    card = compute_scorecard(seq)
    assert card.axis_convergence == "insufficient-data"
    assert card.axis_gotcha_learning == "compounding"
    assert card.axis_enrichment == "compounding"
    # Only two real compounding axes contribute; the inert axis adds nothing.
    assert card.compounding_score == 2


def test_verdict_surfaces_regression_even_when_score_nets_zero():
    """One regressing axis must not be masked by a compounding one (LOW-02)."""
    # convergence compounds (8->2), gotcha regresses (0->4); verify/enrich flat.
    seq = [
        _snap(0, artifacts_changed=8, new_gotchas=0, verify_pass=3, prefix_tokens=100, mem_hits=2),
        _snap(1, artifacts_changed=2, new_gotchas=4, verify_pass=3, prefix_tokens=100, mem_hits=2),
    ]
    card = compute_scorecard(seq)
    assert card.axis_convergence == "compounding"
    assert card.axis_gotcha_learning == "regressing"
    assert card.compounding_score == 0
    assert card.verdict == "regressing"


def test_write_json_includes_caveat_and_insufficient_axes(tmp_path: Path):
    """MEDIUM-02: the caveat travels with the JSON artifact; inert axes are listed."""
    import json

    from bench.report import CAVEAT, write_json

    seq = [_snap(0, artifacts_changed=0), _snap(1, artifacts_changed=0)]
    card = compute_scorecard(seq)
    out = tmp_path / "r.json"
    write_json(card, out)
    payload = json.loads(out.read_text())
    assert payload["caveat"] == CAVEAT
    assert "convergence" in payload["insufficient_data_axes"]


def test_main_does_not_crash_on_unwritable_out(tmp_path: Path):
    """MEDIUM-01: an unwritable --out warns and continues; main returns 0, no raise."""
    import shutil

    from bench.compound_eval import main

    dest = tmp_path / "sample_project"
    shutil.copytree(_FIXTURE_ROOT, dest)
    # A path whose parent is a regular file cannot be created => OSError on write.
    blocker = tmp_path / "blocker"
    blocker.write_text("x")
    bad_out = blocker / "nested" / "results.json"
    rc = main(["--mode", "cheap", "--runs", "2", "--root", str(dest), "--out", str(bad_out)])
    assert rc == 0
    assert not bad_out.exists()


def test_real_loop_refuses_without_bridge(tmp_path: Path, monkeypatch):
    """MEDIUM-04: --mode real fails fast (empty scorecard) when no bridge is available."""
    from io import StringIO

    from rich.console import Console

    import bench.compound_eval as ce

    monkeypatch.setattr(ce, "_bridge_available", lambda: False)
    buf = StringIO()
    console = Console(file=buf, width=120, force_terminal=False)
    card, _judged = ce._real_loop(tmp_path, 3, console=console)
    assert card.snapshots == ()
    assert card.verdict != "compounding"
    assert "requires a usable claude bridge" in buf.getvalue()


def test_real_loop_runs_with_monkeypatched_pipeline(tmp_path: Path, monkeypatch):
    """MEDIUM-04: with the bridge faked-available and pipeline stubbed, _real_loop runs.

    No real LLM call: _run_one is replaced with a no-op so dispatch is exercised
    against a temp copy without touching the source root.
    """
    import shutil
    from io import StringIO

    from rich.console import Console

    import bench.compound_eval as ce
    from bench.metrics import Scorecard

    src = tmp_path / "src"
    shutil.copytree(_FIXTURE_ROOT, src)
    before = _dir_fingerprint(src)

    monkeypatch.setattr(ce, "_bridge_available", lambda: True)
    monkeypatch.setattr(ce, "_run_one", lambda root, *, dry_run: None)

    buf = StringIO()
    console = Console(file=buf, width=120, force_terminal=False)
    card, _judged = ce._real_loop(src, 2, console=console)
    assert isinstance(card, Scorecard)
    assert len(card.snapshots) == 2
    # The source root must be byte-for-byte unchanged (work happened in a temp copy).
    assert _dir_fingerprint(src) == before


def test_cheap_dry_all_four_axes_show_movement(tmp_path: Path):
    """HIGH-03: under cheap-dry, all four axes are genuinely exercised (no all-flat).

    Convergence falls, verify flips fail->pass, gotchas decay, enrichment grows —
    none should read 'flat' or 'insufficient-data' on the synthetic project.
    """
    import shutil
    from io import StringIO

    from rich.console import Console

    from bench.compound_eval import _cheap_loop

    src = tmp_path / "src"
    shutil.copytree(_FIXTURE_ROOT, src)
    buf = StringIO()
    console = Console(file=buf, width=120, force_terminal=False)
    card = _cheap_loop(src, 5, console=console)

    inert = {"flat", "insufficient-data"}
    assert card.axis_convergence not in inert
    assert card.axis_gotcha_learning not in inert
    assert card.axis_verify_non_regression not in inert
    assert card.axis_enrichment not in inert
    assert card.verdict == "compounding"
