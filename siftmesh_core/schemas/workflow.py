"""Workflow schema (C5) - a typed run configuration (PROJECT_CONTEXT §6, GUIDELINES §4).

A :class:`Workflow` declares how a run executes: its mode, hard caps, active
approval gates, evidence-safety posture, agent roster, and stage order. Safety is
encoded in the types: evidence stays hostile/read-only, writes stay run-scoped,
and raw/destructive tooling cannot be enabled. Schema only; the state machine
that runs it is Epic H.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from siftmesh_core.schemas._base import StrictModel
from siftmesh_core.schemas.run import GateName
from siftmesh_core.schemas.task import RetryPolicy

WorkflowMode = Literal["manual", "review_only", "guided", "auto"]
StageName = Literal[
    "init_case",
    "plan",
    "dispatch",
    "collect",
    "critique",
    "report",
    "replay",
]


class WorkflowLimits(StrictModel):
    """Hard caps enforced in full-auto mode (GUIDELINES §4.3)."""

    max_iterations: int = Field(default=3, ge=1)
    max_agent_tasks: int = Field(default=10, ge=1)
    max_parallel_tasks: int = Field(default=3, ge=1)
    max_tool_runtime_seconds: int = Field(default=300, ge=1)


class WorkflowSafety(StrictModel):
    """Non-negotiable safety posture (read-only evidence, no raw shell)."""

    evidence_mode: Literal["read_only"] = "read_only"
    raw_shell: Literal[False] = False
    allow_destructive_tools: Literal[False] = False
    treat_evidence_as_hostile: Literal[True] = True
    restrict_writes_to_run_directory: Literal[True] = True


class Workflow(StrictModel):
    """A typed run configuration (mode + caps + gates + safety + agents + steps)."""

    workflow_id: str
    mode: WorkflowMode
    limits: WorkflowLimits = Field(default_factory=WorkflowLimits)
    safety: WorkflowSafety = Field(default_factory=WorkflowSafety)
    approval_gates: list[GateName] = Field(default_factory=list)
    agents: list[str] = Field(default_factory=list)
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)
    steps: list[StageName] = Field(default_factory=list)
