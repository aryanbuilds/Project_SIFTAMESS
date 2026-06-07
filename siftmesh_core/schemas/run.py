"""Run-state snapshot schema (C4) — the resumable orchestration state.

``RunState`` is a typed, serializable snapshot of where a run is in the
deterministic state machine (PROJECT_CONTEXT §7). It is a *type* here; the state
machine that advances it and persists it atomically lands in Epic H.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from siftmesh_core.schemas._base import StrictModel, UtcDateTime

RunStateName = Literal[
    "init",
    "create_evidence_vault",
    "deep_context",
    "plan",
    "dispatch",
    "collect",
    "critique",
    "decide",
    "report",
    "done",
]

GateName = Literal["plan", "dispatch", "retry", "report"]
GateStatus = Literal["pending", "approved", "rejected", "skipped"]


class RunState(StrictModel):
    """A resumable snapshot of one run's position in the state machine."""

    run_id: str
    state: RunStateName = "init"
    iteration: int = Field(default=0, ge=0)
    agent_tasks_completed: int = Field(default=0, ge=0)
    gates: dict[GateName, GateStatus] = Field(default_factory=dict)
    updated_utc: UtcDateTime | None = None
