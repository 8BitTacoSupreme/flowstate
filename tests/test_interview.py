"""Tests for the interview module — unit tests for data handling."""

from pathlib import Path
from unittest.mock import patch

import pytest

from flowstate.interview import SECTIONS, run_interview
from flowstate.state import FlowStateModel, InterviewAnswers, load_state, save_state


def test_interview_defaults():
    answers = InterviewAnswers()
    assert answers.test_coverage == 80
    assert answers.milestones == []
    assert answers.research_focus == ""


def test_interview_answers_on_state():
    state = FlowStateModel()
    state.interview.research_focus = "gRPC vs REST"
    state.interview.core_problem = "API latency"
    state.interview.milestones = ["Prototype", "MVP", "Launch"]
    state.interview.test_coverage = 95

    assert state.interview.research_focus == "gRPC vs REST"
    assert len(state.interview.milestones) == 3
    assert state.interview.test_coverage == 95


# ── KICK-02: deployment_target field ─────────────────────────────────


def test_interview_answers_has_deployment_target_default():
    """InterviewAnswers has deployment_target with an empty-string default."""
    answers = InterviewAnswers()
    assert hasattr(answers, "deployment_target")
    assert answers.deployment_target == ""


def test_deployment_target_roundtrip(tmp_path: Path):
    """deployment_target survives save_state → load_state."""
    state = FlowStateModel()
    state.interview.deployment_target = "Kubernetes / GKE"
    save_state(state, tmp_path)
    loaded = load_state(tmp_path)
    assert loaded.interview.deployment_target == "Kubernetes / GKE"


def test_deployment_target_in_sections():
    """The (deployment_target, ...) tuple is present in SECTIONS so init + kickoff share it."""
    all_fields = [field for section in SECTIONS for field, _ in section["questions"]]
    assert "deployment_target" in all_fields


def test_deployment_target_question_in_discipline_section():
    """deployment_target is wired to the discipline/management section (not a random section)."""
    for section in SECTIONS:
        fields_in_section = [f for f, _ in section["questions"]]
        if "deployment_target" in fields_in_section:
            assert section["key"] in ("discipline", "management")
            return
    pytest.fail("deployment_target not found in any SECTIONS entry")


# ── KICK-02: test_coverage validation ─────────────────────────────────


def test_test_coverage_validation_reprompts_on_out_of_range():
    """test_coverage outside 0-100 is rejected and re-prompted until in range."""
    state = FlowStateModel()
    # Simulate user entering 150 first (invalid), then 80 (valid)
    with (
        patch("flowstate.interview.IntPrompt.ask", side_effect=[150, 80]) as mock_ask,
        patch("flowstate.interview.Prompt.ask", return_value=""),
    ):
        run_interview(state)
    # Final value must be the valid one (80)
    assert state.interview.test_coverage == 80
    # IntPrompt.ask must have been called at least twice for test_coverage
    assert mock_ask.call_count >= 2


def test_test_coverage_valid_on_first_try():
    """test_coverage in range requires only one prompt call."""
    state = FlowStateModel()
    with (
        patch("flowstate.interview.IntPrompt.ask", return_value=90) as mock_ask,
        patch("flowstate.interview.Prompt.ask", return_value=""),
    ):
        run_interview(state)
    assert state.interview.test_coverage == 90
    assert mock_ask.call_count == 1


# ── KICK-02: deployment_target branching ──────────────────────────────


def test_deployment_target_asked_when_architecture_pattern_set():
    """deployment_target follow-up is asked when architecture_pattern is non-empty.

    The mock returns "hexagonal" for the architecture_pattern question so the
    branching guard sees a non-empty value when it evaluates deployment_target.
    """
    state = FlowStateModel()

    prompt_calls: list[str] = []

    def fake_prompt(question, **kwargs):
        prompt_calls.append(question)
        # Return a non-empty architecture pattern so deployment_target is asked
        if "architectural pattern" in question.lower():
            return "hexagonal"
        return ""

    with (
        patch("flowstate.interview.IntPrompt.ask", return_value=80),
        patch("flowstate.interview.Prompt.ask", side_effect=fake_prompt),
    ):
        run_interview(state)

    deployment_calls = [q for q in prompt_calls if "deploy" in q.lower() or "run" in q.lower()]
    assert len(deployment_calls) >= 1, (
        f"Expected deployment_target prompt but got calls: {prompt_calls}"
    )


def test_deployment_target_skipped_when_architecture_pattern_empty():
    """deployment_target is NOT asked when architecture_pattern is empty."""
    state = FlowStateModel()
    state.interview.architecture_pattern = ""

    prompt_calls: list[str] = []

    def fake_prompt(question, **kwargs):
        prompt_calls.append(question)
        # architecture_pattern answer is empty — deployment_target must not appear
        return ""

    with (
        patch("flowstate.interview.IntPrompt.ask", return_value=80),
        patch("flowstate.interview.Prompt.ask", side_effect=fake_prompt),
    ):
        run_interview(state)

    deployment_calls = [q for q in prompt_calls if "deploy" in q.lower() or "run" in q.lower()]
    assert len(deployment_calls) == 0, (
        f"Expected NO deployment_target prompt but got: {deployment_calls}"
    )
