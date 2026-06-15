"""Tool-call request + critic verdict schemas (C4) - types only.

``ToolCall`` is the typed request to run a tool; ``CriticVerdict`` is the
deterministic Critic's ruling on a result. The engines that *produce* these - the
audited executor (Epic D) and the Critic (Epic G) - live elsewhere.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from siftmesh_core.schemas._base import StrictModel, UtcDateTime


class ToolCall(StrictModel):
    """A request to invoke a typed forensic tool."""

    tool_call_id: str
    tool_name: str
    args: dict[str, Any] = Field(default_factory=dict)
    requested_utc: UtcDateTime


CriticVerdictType = Literal[
    "accepted",
    "accepted_with_downgrade",
    "retry_required",
    "escalation_required",
    "human_review_required",
    "rejected",
]


class CriticVerdict(StrictModel):
    """The Critic's deterministic ruling on a result and its claims."""

    verdict: CriticVerdictType
    reasons: list[str] = Field(default_factory=list)
    affected_claim_ids: list[str] = Field(default_factory=list)
    # Epic G persistence - optional so the bare (verdict + reasons) form still validates.
    # The critic fills all three when it writes a verdict to audit/critic_verdicts.jsonl.
    task_id: str | None = None
    verdict_id: str | None = None  # deterministic VERDICT-NNN from ledger length
    decided_utc: UtcDateTime | None = None
