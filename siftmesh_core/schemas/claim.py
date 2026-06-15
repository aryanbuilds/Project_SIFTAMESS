"""Claim schema + evidence-discipline validators (C2) - the hallucination firewall.

A :class:`Claim` cannot be constructed with status ``confirmed`` / ``inferred`` /
``contradicted`` unless it carries its evidence anchor (``tool_call_id`` AND
``source_sha256``, plus ``source_artifact`` + ``tool_name``). The one exception is
status ``unsupported`` - the explicit "agent said it, evidence is missing" record
that is logged to its own ledger and never reported as fact. This encodes
"log, don't delete, never report as fact" directly in the type system.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal, Self

from pydantic import Field, model_validator

from siftmesh_core.schemas._base import Sha256, StrictModel, UtcDateTime

ClaimStatus = Literal["confirmed", "inferred", "contradicted", "unsupported"]

# Statuses that assert something about the evidence and so must be anchored.
_ANCHORED_STATUSES: tuple[ClaimStatus, ...] = ("confirmed", "inferred", "contradicted")

# The evidence anchor a non-``unsupported`` claim must carry.
_EVIDENCE_FIELDS = ("source_artifact", "source_sha256", "tool_name", "tool_call_id")


class Claim(StrictModel):
    """One evidence-anchored finding (or an explicit ``unsupported`` record)."""

    claim_id: str
    task_id: str
    status: ClaimStatus
    claim: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_type: str
    source_artifact: str | None = None
    source_sha256: Sha256 | None = None
    tool_name: str | None = None
    tool_call_id: str | None = None
    timestamp_utc: UtcDateTime | None = None
    supporting_evidence_refs: list[str] = Field(default_factory=list)
    contradicting_evidence_refs: list[str] = Field(default_factory=list)
    requires_human_review: bool = False

    @model_validator(mode="after")
    def _require_evidence_unless_unsupported(self) -> Self:
        """Reject an anchored claim that lacks its evidence references."""
        if self.status == "unsupported":
            return self
        missing = [name for name in _EVIDENCE_FIELDS if not getattr(self, name)]
        if missing:
            raise ValueError(
                f"claim {self.claim_id!r} (status {self.status!r}) requires evidence "
                f"references; missing: {', '.join(missing)}"
            )
        return self


def validate_claim_evidence(claim: Claim | Mapping[str, Any]) -> list[str]:
    """Return evidence-discipline violations for a claim (empty list = clean).

    The non-raising counterpart to the model validator: the Critic (Epic G) uses
    this to *grade* a claim - including raw, not-yet-validated agent output passed
    as a mapping - rather than reject it at parse time.
    """
    if isinstance(claim, Claim):
        status: Any = claim.status
        values = {name: getattr(claim, name) for name in _EVIDENCE_FIELDS}
    else:
        status = claim.get("status")
        values = {name: claim.get(name) for name in _EVIDENCE_FIELDS}

    if status == "unsupported":
        return []

    problems: list[str] = []
    if status not in _ANCHORED_STATUSES:
        problems.append(f"invalid or missing status: {status!r}")
    problems.extend(f"missing {name}" for name in _EVIDENCE_FIELDS if not values[name])
    return problems
