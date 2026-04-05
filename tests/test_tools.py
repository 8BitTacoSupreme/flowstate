"""Tests for tool adapters."""

from pathlib import Path

from flowstate.state import InterviewAnswers
from flowstate.tools.autoresearch import AutoresearchAdapter
from flowstate.tools.gsd_adapter import GSDAdapter
from flowstate.tools.gstack import GstackAdapter
from flowstate.tools.superpowers import SuperpowersAdapter


def test_autoresearch_dry_run(tmp_path: Path):
    adapter = AutoresearchAdapter(root=tmp_path, dry_run=True)
    answers = InterviewAnswers(research_focus="websocket libraries")
    result = adapter.execute(answers)

    assert result.success
    assert (tmp_path / "research" / "report.md").exists()
    content = (tmp_path / "research" / "report.md").read_text()
    assert "websocket libraries" in content


def test_gstack_dry_run(tmp_path: Path):
    adapter = GstackAdapter(root=tmp_path, dry_run=True)
    answers = InterviewAnswers(core_problem="Slow deploys", ten_x_vision="One-click shipping")

    env_result = adapter.init_stack()
    assert env_result.success

    oh_result = adapter.office_hours(answers)
    assert oh_result.success
    assert (tmp_path / "research" / "strategy.md").exists()


def test_gsd_dry_run(tmp_path: Path):
    adapter = GSDAdapter(root=tmp_path, dry_run=True)
    answers = InterviewAnswers(milestones=["Alpha", "Beta", "GA"])
    result = adapter.new_project(answers)

    assert result.success
    content = (tmp_path / "ROADMAP.md").read_text()
    assert "Alpha" in content
    assert "Beta" in content


def test_superpowers_dry_run(tmp_path: Path):
    adapter = SuperpowersAdapter(root=tmp_path, dry_run=True)
    answers = InterviewAnswers(test_coverage=90, architecture_pattern="hexagonal")
    result = adapter.init_repo(answers)

    assert result.success
    assert "90%" in result.output
    assert "hexagonal" in result.output


def test_superpowers_branch_detection():
    adapter = SuperpowersAdapter(root=Path("."), dry_run=True)
    assert adapter.should_branch("Harden authentication")
    assert adapter.should_branch("Stabilize API layer")
    assert not adapter.should_branch("Add user login")
    assert not adapter.should_branch("Build dashboard")
