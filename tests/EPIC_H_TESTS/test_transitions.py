"""H2 — frozen transition table: legal transitions allowed, illegal rejected."""

from __future__ import annotations

import pytest
from siftmesh_core.orchestrator.state_machine import (
    IllegalTransitionError,
    legal_successors,
    next_state,
    step,
)


def test_legal_transition_allowed() -> None:
    assert step("init", "create_evidence_vault") == "create_evidence_vault"
    assert step("plan", "dispatch") == "dispatch"
    assert step("decide", "report") == "report"
    assert step("report", "done") == "done"


def test_illegal_transition_rejected() -> None:
    with pytest.raises(IllegalTransitionError):
        step("plan", "collect")  # plan cannot jump to collect
    with pytest.raises(IllegalTransitionError):
        step("init", "done")
    with pytest.raises(IllegalTransitionError):
        step("done", "report")  # terminal has no successor


def test_linear_spine_single_successor() -> None:
    assert next_state("create_evidence_vault") == "deep_context"
    assert next_state("dispatch") == "collect"
    assert next_state("collect") == "critique"
    assert next_state("critique") == "decide"


def test_plan_branches_on_review_only() -> None:
    assert next_state("plan") == "dispatch"
    assert next_state("plan", review_only=True) == "done"


def test_decide_branches_on_decision() -> None:
    assert next_state("decide", decision="done") == "report"
    assert next_state("decide", decision="retry") == "dispatch"
    assert next_state("decide", decision="follow_up") == "dispatch"
    # escalate / human_review / None -> halt at decide (no transition)
    assert next_state("decide", decision="escalate") == "decide"
    assert next_state("decide", decision="human_review") == "decide"
    assert next_state("decide") == "decide"


def test_terminal_is_sink() -> None:
    assert legal_successors("done") == frozenset()
    assert next_state("done") == "done"
