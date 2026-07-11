"""E2E smoke test: the "harness of harnesses works end-to-end" acceptance gate (HAR-05).

Exercises EVERY --layers arm's plumbing through bench.compound_eval.main in
--mode cheap ONLY, so no live LLM/claude binary and no network are ever required
(CI-safe). Also asserts the harness fails loud (_EXIT_PRODUCER_ABSENT) when an
arm's required producer artifact is absent, rather than silently reporting a
bare number for a layer it never measured.
"""

from __future__ import annotations

from pathlib import Path

import bench.compound_eval as compound_eval
from bench.project import scaffold

# Arms with no producer requirement — full/memory/none must always run green
# under --mode cheap regardless of what is (or isn't) on disk.
_PRODUCERLESS_ARMS = ("full", "none", "memory")

# Arms gated on a producer artifact.
_PRODUCER_ARMS = ("pack", "wiki")


def _run(root: Path, arm: str) -> int:
    return compound_eval.main(
        ["--mode", "cheap", "--layers", arm, "--runs", "1", "--root", str(root)]
    )


def test_producerless_arms_run_green(tmp_path: Path) -> None:
    """full/memory/none have no producer requirement and always pass the gate."""
    scaffold(tmp_path)
    for arm in _PRODUCERLESS_ARMS:
        assert _run(tmp_path, arm) == 0, f"arm {arm!r} should run green with no producer"


def test_producer_arms_fail_loud_when_absent(tmp_path: Path) -> None:
    """pack/wiki with NO producer artifact on disk must exit _EXIT_PRODUCER_ABSENT."""
    scaffold(tmp_path)
    for arm in _PRODUCER_ARMS:
        rc = _run(tmp_path, arm)
        assert rc == compound_eval._EXIT_PRODUCER_ABSENT, (
            f"arm {arm!r} with an absent producer should exit "
            f"{compound_eval._EXIT_PRODUCER_ABSENT}, got {rc}"
        )


def test_producer_arms_run_green_when_present(tmp_path: Path) -> None:
    """pack/wiki with a real (non-empty) producer artifact must run green.

    Producer artifacts are written directly (no repomix/npx subprocess) so this
    stays CI-safe: it proves the arm's plumbing runs once its producer is
    satisfied, without requiring any external tool on PATH.
    """
    scaffold(tmp_path)

    pack_path = tmp_path / ".planning" / "codebase" / "repomix-pack.xml"
    pack_path.parent.mkdir(parents=True, exist_ok=True)
    pack_path.write_text("<repomix/>")

    wiki_dir = tmp_path / ".planning" / "codebase" / "wiki"
    wiki_dir.mkdir(parents=True, exist_ok=True)
    (wiki_dir / "overview.md").write_text("# Overview\n\nReal wiki content for the smoke test.\n")

    for arm in _PRODUCER_ARMS:
        assert _run(tmp_path, arm) == 0, f"arm {arm!r} should run green once its producer exists"


def test_every_arm_covered() -> None:
    """Guard against a future arm shipping without an E2E smoke (T-18-06).

    The union of arms exercised across this module's tests must equal the full
    arm vocabulary in bench.compound_eval._ARM_PRODUCERS.
    """
    tested_arms = set(_PRODUCERLESS_ARMS) | set(_PRODUCER_ARMS)
    assert tested_arms == set(compound_eval._ARM_PRODUCERS)
