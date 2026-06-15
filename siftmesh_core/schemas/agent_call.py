"""Agent-call audit record (Epic F, F6) - one line per dispatch.

Every executor dispatch appends an :class:`AgentCall` to ``audit/agent_calls.jsonl``
so a run's agent activity is replayable: which profile was requested, which adapter
actually ran (and whether it fell back to the deterministic floor), the attempt, and
the outcome. Distinct from ``tool_calls.jsonl`` (per-tool provenance) - this is the
per-task/per-agent layer.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from siftmesh_core.schemas._base import StrictModel, UtcDateTime

AgentCallStatus = Literal["success", "error", "retry_required", "fell_back"]


class AgentCall(StrictModel):
    """One executor dispatch's audit record."""

    agent_call_id: str  # deterministic AGENT-NNN from ledger length
    task_id: str
    profile: str  # requested assigned_agent_profile
    adapter: str  # adapter class that ran
    backend: str  # "real" | "claude_headless" | "opencode" | "generic_shell"
    attempt: int = Field(default=1, ge=1)
    start_time_utc: UtcDateTime
    end_time_utc: UtcDateTime
    status: AgentCallStatus
    fell_back_from: str | None = None  # set when a live profile fell to the floor
