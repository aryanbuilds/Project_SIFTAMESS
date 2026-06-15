"""Investigation-plan schema (E4) - the ordered step graph the planner emits.

A :class:`InvestigationPlan` is the deterministic output of ``siftmesh plan``: an
ordered DAG of steps (deep-context -> one executor per actionable artifact ->
timeline -> critique -> report). It is deliberately richer than
:class:`~siftmesh_core.schemas.workflow.Workflow` (whose ``steps`` is a flat list
of coarse stage names) because every executor/timeline step must bind to a real
manifest artifact and a single allowlisted tool.

There is **no wall-clock field**: the plan is a pure function of the run id, case
id, and manifest, so two ``plan`` runs over the same manifest produce byte-identical
YAML. Timing lives in ``run_id`` and ``audit/orchestration_events.jsonl``.
"""

from __future__ import annotations

from typing import Literal, Self

from pydantic import Field, model_validator

from siftmesh_core.schemas._base import StrictModel

# deep_context/critique/report are case-wide stages; executor/timeline bind to artifacts.
PlanStepKind = Literal["deep_context", "executor", "timeline", "critique", "report"]

# Step kinds that dispatch a tool against a specific artifact (need task+tool+artifact).
_BOUND_KINDS: tuple[PlanStepKind, ...] = ("executor", "timeline")


class PlanStep(StrictModel):
    """One node in the investigation DAG."""

    step_id: str
    kind: PlanStepKind
    description: str
    depends_on: list[str] = Field(default_factory=list)
    task_id: str | None = None
    tool: str | None = None
    # Manifest-relative artifact paths the step's tool consumes (one for an executor,
    # all timeline-capable artifacts for a timeline step; empty for non-bound kinds).
    input_artifacts: list[str] = Field(default_factory=list)


class InvestigationPlan(StrictModel):
    """An ordered step graph proposed by the planner (never executed by it)."""

    plan_id: str
    case_id: str
    template: str
    review_only: bool = False
    artifact_count: int = Field(ge=0)
    steps: list[PlanStep] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_graph(self) -> Self:
        """Unique ids, acyclic deps, and kind-correct artifact binding.

        Dependencies must reference an *earlier* step (already ``seen``), which
        enforces a topological order and so forbids both forward references and
        cycles for free - the "ordered step graph" the docstring promises.
        """
        ids = [s.step_id for s in self.steps]
        if len(ids) != len(set(ids)):
            raise ValueError("investigation plan has duplicate step_id(s)")
        seen: set[str] = set()
        for step in self.steps:
            for dep in step.depends_on:
                if dep not in seen:
                    raise ValueError(
                        f"step {step.step_id!r} depends on {dep!r} which is not an earlier "
                        f"step (forward reference or cycle)"
                    )
            bound = step.kind in _BOUND_KINDS
            has_binding = bool(step.task_id and step.tool and step.input_artifacts)
            if bound and not has_binding:
                raise ValueError(
                    f"{step.kind} step {step.step_id!r} must set task_id + tool + input_artifacts"
                )
            if not bound and (step.task_id or step.tool or step.input_artifacts):
                raise ValueError(
                    f"{step.kind} step {step.step_id!r} must not set task_id/tool/input_artifacts"
                )
            seen.add(step.step_id)
        return self
