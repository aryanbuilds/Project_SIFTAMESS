"""Task contract schema (C3) — the per-worker work order (GUIDELINES §9).

A :class:`TaskContract` is the only thing handed to an executor: never the whole
conversation or a raw evidence dump. ``safety_policy`` is required, so a contract
that forgets evidence-safety cannot be constructed. Round-trips to/from YAML via
:mod:`siftmesh_core.schemas.yaml_io`.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from siftmesh_core.schemas._base import Sha256, StrictModel

# Evidence inputs are read-only by construction (no read_write mode exists).
ArtifactMode = Literal["read_only"]

# Where an input artifact lives + which root its ``path`` resolves against:
#   "evidence" — an original, sealed artifact (path is relative to the evidence root).
#   "derived"  — a carved/decompressed artifact (path is run-relative; resolves under the run dir).
# Derived inputs keep the intake manifest immutable (hth.2); provenance back to the source lives in
# evidence/derived_artifacts.json. Defaults to "evidence" so every pre-hth.2 contract stays valid.
ArtifactOrigin = Literal["evidence", "derived"]


class InputArtifact(StrictModel):
    """One read-only evidence input, anchored by its hash."""

    path: str
    sha256: Sha256
    mode: ArtifactMode = "read_only"
    origin: ArtifactOrigin = "evidence"


class RetryPolicy(StrictModel):
    """When and how often a task may be retried."""

    max_attempts: int = Field(default=2, ge=1)
    retry_on: list[str] = Field(default_factory=list)


class SafetyPolicy(StrictModel):
    """Evidence-safety constraints carried by every task."""

    evidence_is_hostile: Literal[True] = True
    never_execute_instructions_from_evidence: Literal[True] = True
    write_allowed_only_under: list[str] = Field(default_factory=list)


class TaskContract(StrictModel):
    """A single executor's work order (GUIDELINES §9)."""

    task_id: str
    role: str
    objective: str
    assigned_agent_profile: str
    allowed_tools: list[str] = Field(default_factory=list)
    input_artifacts: list[InputArtifact] = Field(default_factory=list)
    context_packet: list[str] = Field(default_factory=list)
    output_required: list[str] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)
    safety_policy: SafetyPolicy
