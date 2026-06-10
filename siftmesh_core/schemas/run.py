"""Run-state snapshot schema (C4) — the resumable orchestration state.

``RunState`` is a typed, serializable snapshot of where a run is in the
deterministic state machine (PROJECT_CONTEXT §7). The Epic-H state machine
advances it and persists it atomically (temp+fsync+rename) on every transition
to ``run_state.json`` (see ``orchestrator/run_state_store.py``), so a killed run
resumes from exactly where it stopped.
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

# The four `siftmesh run` automation modes (CLAUDE.md §11 / PROJECT_CONTEXT §6).
RunMode = Literal["manual", "review_only", "auto_human_loop", "auto"]

GateName = Literal["plan", "dispatch", "retry", "report"]
GateStatus = Literal["pending", "approved", "rejected", "skipped"]


class PerTaskState(StrictModel):
    """Per-task attempt bookkeeping (distinct from the global ``iteration`` counter)."""

    attempt: int = Field(default=1, ge=1)
    max_attempts: int = Field(default=2, ge=1)
    status: str = "pending"  # last collect/critic outcome for the task


class RunState(StrictModel):
    """A resumable snapshot of one run's position in the state machine."""

    run_id: str
    state: RunStateName = "init"
    mode: RunMode = "manual"
    iteration: int = Field(default=0, ge=0)  # global self-correction loop counter
    max_iterations: int = Field(default=3, ge=1)
    agent_tasks_completed: int = Field(default=0, ge=0)
    per_task: dict[str, PerTaskState] = Field(default_factory=dict)
    pending_dispatch: list[str] = Field(default_factory=list)  # task_ids to (re)dispatch next loop
    # Tasks the critic flagged for human review / escalation that full-auto quarantined to keep
    # running (their claims were already kept out of the findings ledger; they never become facts).
    quarantined_tasks: list[str] = Field(default_factory=list)
    gates: dict[GateName, GateStatus] = Field(default_factory=dict)
    blocked_gate: GateName | None = None  # set when the engine halts awaiting approval
    terminal: bool = False
    updated_utc: UtcDateTime | None = None
