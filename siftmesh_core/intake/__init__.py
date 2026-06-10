"""Operator-intake helpers (TRUSTED context, distinct from hostile evidence).

The incident brief is the operator's investigation OBJECTIVE — trusted context, NOT hostile
evidence. It is designated explicitly (``--brief``), kept out of the manifest's hostile ``files``
set, and rendered into ``context/incident_brief.md``. See :mod:`siftmesh_core.intake.brief`.
"""

from __future__ import annotations

from siftmesh_core.intake.brief import (
    SUPPORTED_SUFFIXES,
    BriefIntakeError,
    derive_objective,
    extract_brief_text,
    ingest_brief,
)

__all__ = [
    "SUPPORTED_SUFFIXES",
    "BriefIntakeError",
    "derive_objective",
    "extract_brief_text",
    "ingest_brief",
]
