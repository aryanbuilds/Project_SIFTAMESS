"""Read-only posture recorder (B3).

Records the original evidence location and the read-only *posture* SIFTMesh
guarantees by construction - it opens originals read-only and never writes to a
source. This is ``enforcement: posture_only``; it is **not** an OS-level
read-only mount (``mount -o ro`` / ``blockdev --setro``), which is a documented
Linux enhancement deferred to a later epic.
"""

from __future__ import annotations

import json
from pathlib import Path

from siftmesh_core.evidence.path_policy import safe_write_path

_POSTURE_NOTE = (
    "Records intended read-only posture: SIFTMesh opens originals read-only and "
    "never writes to a source. This is NOT OS-level RO-mount enforcement "
    "(mount -o ro / blockdev --setro), which is deferred to a later epic."
)


def write_readonly_record(
    evidence_root: Path | str,
    run_root: Path | str,
    *,
    file_count: int,
) -> Path:
    """Write ``evidence/readonly_mounts.json`` describing the read-only posture."""
    evidence = Path(evidence_root).resolve()
    record = {
        "enforcement": "posture_only",
        "note": _POSTURE_NOTE,
        "sources": [{"path": str(evidence), "access": "read_only", "file_count": file_count}],
    }
    target = safe_write_path(
        run_root, Path("evidence") / "readonly_mounts.json", evidence_root=evidence
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target
