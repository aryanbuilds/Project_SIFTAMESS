"""Task-result envelope (Epic F) - an executor's per-task output.

A :class:`TaskResult` is what an adapter writes to ``results/TASK-XXX.result.json``
(the ``output_required`` of every executor contract, CLAUDE.md §8). It carries the
evidence-anchored :class:`~siftmesh_core.schemas.claim.Claim` objects the executor
produced, the tool calls that backed them, and an honest record of *which* adapter
actually ran (``adapter`` may differ from the requested ``profile`` when a live
adapter fell back to the deterministic floor). The critic (Epic G) reads this file.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from siftmesh_core.schemas._base import StrictModel, UtcDateTime
from siftmesh_core.schemas.claim import Claim

# success = all tools ran and claims are anchored; error = fatal/fail-closed;
# retry_required = a genuine recoverable cause (decision belongs to Epic G decide()).
TaskResultStatus = Literal["success", "error", "retry_required"]


class TaskResult(StrictModel):
    """One executor task's structured output (the contract's required result file)."""

    task_id: str
    profile: str  # the requested assigned_agent_profile
    adapter: str  # the adapter that actually ran (differs from profile on fall-back)
    attempt: int = Field(default=1, ge=1)
    status: TaskResultStatus
    tool_call_ids: list[str] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)
    started_utc: UtcDateTime
    ended_utc: UtcDateTime
    errors: list[str] = Field(default_factory=list)
    # The genuine cause when status == "retry_required" (Epic G decides what to do).
    retry_cause: str | None = None
