"""Critic ledger records (Epic G) — contradiction, confidence-change, retry.

Typed JSONL ledger records the deterministic critic writes alongside its verdicts:
``ContradictionRecord`` (two claims that disagree), ``ConfidenceChange`` (an audited
downgrade — append-only, never mutating the original claim line), and ``RetryRecord``
(a tightened-contract retry the self-correction loop generated).
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from siftmesh_core.schemas._base import StrictModel, UtcDateTime

ContradictionRule = Literal["same_subject_opposite_assertion", "same_artifact_field_value_mismatch"]


class ContradictionRecord(StrictModel):
    """Two anchored claims that disagree (deterministically detected, no LLM)."""

    contradiction_id: str  # deterministic CONTRA-NNN
    task_id: str
    claim_id_a: str
    claim_id_b: str
    rule: ContradictionRule
    subject: str  # the shared key/subject that collided (for replay/grep)
    detail: str  # human-readable "<a> vs <b>"
    detected_utc: UtcDateTime


class ConfidenceChange(StrictModel):
    """An audited confidence downgrade (append-only; never rewrites the claim line)."""

    change_id: str  # deterministic CONF-NNN
    claim_id: str
    task_id: str
    from_confidence: float = Field(ge=0.0, le=1.0)
    to_confidence: float = Field(ge=0.0, le=1.0)
    reason: str
    changed_utc: UtcDateTime


class RetryRecord(StrictModel):
    """A self-correction retry: a task re-dispatched with a tightened contract."""

    retry_id: str  # deterministic RETRY-NNN
    task_id: str
    from_attempt: int = Field(ge=1)
    to_attempt: int = Field(ge=2)
    cause: str  # the decide()/verdict reason
    tightened_criteria: list[str] = Field(default_factory=list)
    decided_utc: UtcDateTime
