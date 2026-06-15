"""Evidence manifest schema (C6, pulled forward for Epic B's B4/B5).

``EvidenceManifest`` is the typed contract the evidence vault serializes to
``evidence/evidence_manifest.json``; ``EvidenceFile`` is one hashed artifact.
The I/O lives in ``evidence/manifest.py`` - these are types only.
"""

from __future__ import annotations

from pydantic import Field

from siftmesh_core.schemas._base import Sha256, StrictModel, UtcDateTime


class EvidenceFile(StrictModel):
    """One ingested artifact's integrity facts (relative to the evidence root)."""

    path: str
    sha256: Sha256
    size_bytes: int = Field(ge=0)
    mtime_utc: UtcDateTime
    evidence_type: str


class EvidenceManifest(StrictModel):
    """Manifest of all ingested artifacts for one run.

    ``incident_objective`` / ``incident_brief_path`` record an OPERATOR-supplied incident
    briefing (the investigation objective) when one is given via ``--brief``. The brief is
    TRUSTED operator context, NOT hostile evidence - it is deliberately kept out of ``files``
    (the hostile set the artifact router consumes) and lives under ``context/`` instead. Both
    default to ``None`` so manifests without a brief stay valid.
    """

    case_id: str
    run_id: str
    created_utc: UtcDateTime
    tool_version: str
    files: list[EvidenceFile] = Field(default_factory=list)
    incident_objective: str | None = None
    incident_brief_path: str | None = None
