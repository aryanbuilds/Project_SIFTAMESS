"""G4 - the pure decide() function: one assertion per CLAUDE §12 rule."""

from __future__ import annotations

from siftmesh_core.orchestrator.decide import decide


def test_decide_done_on_accepted() -> None:
    assert decide("accepted", attempt=1, max_attempts=2).action == "done"
    assert decide("accepted_with_downgrade", attempt=1, max_attempts=2).action == "done"


def test_decide_retry_when_attempt_below_max() -> None:
    d = decide("retry_required", attempt=1, max_attempts=2)
    assert d.action == "retry"
    assert d.tighten_success_criteria is True


def test_decide_escalates_when_retry_budget_exhausted() -> None:
    assert decide("retry_required", attempt=2, max_attempts=2).action == "escalate"


def test_decide_escalates_on_second_failure() -> None:
    d = decide("retry_required", attempt=1, max_attempts=2, prior_attempts_failed=True)
    assert d.action == "escalate"


def test_decide_escalates_on_contradiction() -> None:
    assert decide("escalation_required", attempt=1, max_attempts=2).action == "escalate"
    assert decide("accepted", attempt=1, max_attempts=2, has_contradiction=True).action == "done"
    # contradiction with a non-accepted verdict escalates
    assert (
        decide("retry_required", attempt=1, max_attempts=2, has_contradiction=True).action
        == "escalate"
    )


def test_decide_human_on_max_iterations() -> None:
    assert (
        decide("retry_required", attempt=1, max_attempts=2, iteration=3, max_iterations=3).action
        == "human_review"
    )


def test_decide_human_on_injection() -> None:
    assert decide("human_review_required", attempt=1, max_attempts=2).action == "human_review"
    assert (
        decide("accepted", attempt=1, max_attempts=2, injection_affected=True).action
        == "human_review"
    )


def test_decide_human_on_evidence_mismatch() -> None:
    assert (
        decide("accepted", attempt=1, max_attempts=2, evidence_mismatch=True).action
        == "human_review"
    )


def test_decide_human_on_unsupported_affects_report() -> None:
    assert (
        decide("retry_required", attempt=1, max_attempts=2, unsupported_affects_report=True).action
        == "human_review"
    )


def test_decide_escalates_on_rejected() -> None:
    assert decide("rejected", attempt=1, max_attempts=2).action == "escalate"


def test_decide_is_pure_returns_decision() -> None:
    # Pure: only scalars/booleans in; a Decision out; no path/run args exist to do I/O.
    d = decide("accepted", attempt=1, max_attempts=2)
    assert d.action == "done" and d.reason
