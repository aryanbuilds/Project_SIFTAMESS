"""Evidence manifest schema (C6, pulled forward for Epic B's B4/B5).

``EvidenceManifest`` is the typed contract the evidence vault serializes to
``evidence/evidence_manifest.json``; ``EvidenceFile`` is one hashed artifact.
The I/O lives in ``evidence/manifest.py`` — these are types only.
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
    """Manifest of all ingested artifacts for one run."""

    case_id: str
    run_id: str
    created_utc: UtcDateTime
    tool_version: str
    files: list[EvidenceFile] = Field(default_factory=list)
