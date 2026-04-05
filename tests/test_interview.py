"""Tests for the interview module — unit tests for data handling."""

from flowstate.state import FlowStateModel, InterviewAnswers


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
