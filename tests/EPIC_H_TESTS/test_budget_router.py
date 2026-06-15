"""H9 - static budget router: escalate cheap→strong on retry, graceful default."""

from __future__ import annotations

from siftmesh_core.orchestrator.budget_router import select_profile


def test_router_escalates_on_retry() -> None:
    decision = select_profile("claude_low_cost", escalate=True)
    assert decision.selected_profile == "claude_high_reasoning"
    assert decision.escalated is True


def test_router_no_escalation_keeps_base() -> None:
    decision = select_profile("claude_low_cost", escalate=False)
    assert decision.selected_profile == "claude_low_cost"
    assert decision.escalated is False


def test_router_graceful_when_no_strong_tier() -> None:
    # the deterministic floor has no stronger tier -> fall back to itself (no fake escalation)
    decision = select_profile("deterministic_executor", escalate=True)
    assert decision.selected_profile == "deterministic_executor"
    assert decision.escalated is False
