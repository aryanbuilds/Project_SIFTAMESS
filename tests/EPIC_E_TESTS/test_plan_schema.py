"""InvestigationPlan / PlanStep validator tests (E4 schema)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from siftmesh_core.schemas.plan import InvestigationPlan, PlanStep


def _plan(steps: list[PlanStep]) -> InvestigationPlan:
    return InvestigationPlan(
        plan_id="RUN-X",
        case_id="c",
        template="windows_initial_triage",
        artifact_count=0,
        steps=steps,
    )


def test_minimal_plan_validates() -> None:
    _plan([PlanStep(step_id="step-001", kind="deep_context", description="dc")])


def test_duplicate_step_ids_rejected() -> None:
    with pytest.raises(ValidationError, match="duplicate step_id"):
        _plan(
            [
                PlanStep(step_id="step-001", kind="deep_context", description="a"),
                PlanStep(step_id="step-001", kind="critique", description="b"),
            ]
        )


def test_unknown_dependency_rejected() -> None:
    with pytest.raises(ValidationError, match="unknown step"):
        _plan([PlanStep(step_id="step-001", kind="report", description="r", depends_on=["nope"])])


def test_executor_step_requires_binding() -> None:
    with pytest.raises(ValidationError, match="must set task_id"):
        _plan([PlanStep(step_id="step-001", kind="executor", description="e")])


def test_non_bound_step_forbids_binding() -> None:
    with pytest.raises(ValidationError, match="must not set"):
        _plan(
            [PlanStep(step_id="step-001", kind="critique", description="c", tool="build_timeline")]
        )
