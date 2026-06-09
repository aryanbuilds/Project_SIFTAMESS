"""Derived-artifacts registry (B5).

Append-only map of every derived/output file → its source artifact, the source's
SHA-256, and the producing ``tool_call_id``. Originals are never mutated; this is
the provenance chain for anything SIFTMesh generates from evidence. At
``init-case`` the registry is created empty (no derived artifacts exist yet).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from siftmesh_core.evidence.path_policy import safe_write_path


@dataclass(frozen=True)
class DerivedArtifact:
    """One derived file's provenance back to its source evidence."""

    derived_path: str  # run-relative POSIX path
    source_artifact: str  # evidence-relative POSIX path
    source_sha256: str
    tool_call_id: str
    derived_sha256: str | None = None
    # Optional provenance when the derived file was extracted from inside a disk
    # image (Epic D deepening). Defaulting to None keeps older records loadable.
    extraction_source_path: str | None = None  # NTFS path inside the image
    extraction_inode: str | None = None  # TSK metadata address (e.g. "65-128-1")
    extraction_method: str | None = None  # e.g. "sleuthkit_icat"


def _registry_path(run_root: Path | str, evidence_root: Path | str | None = None) -> Path:
    return safe_write_path(
        run_root, Path("evidence") / "derived_artifacts.json", evidence_root=evidence_root
    )


def init_registry(run_root: Path | str, *, evidence_root: Path | str | None = None) -> Path:
    """Create an empty ``derived_artifacts.json`` if absent; return its path."""
    target = _registry_path(run_root, evidence_root)
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        target.write_text(json.dumps({"derived": []}, indent=2) + "\n", encoding="utf-8")
    return target


def append_derived(
    run_root: Path | str,
    artifact: DerivedArtifact,
    *,
    evidence_root: Path | str | None = None,
) -> Path:
    """Append one :class:`DerivedArtifact` record to the registry."""
    target = init_registry(run_root, evidence_root=evidence_root)
    data = json.loads(target.read_text(encoding="utf-8"))
    data["derived"].append(asdict(artifact))
    target.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return target


def read_derived(run_root: Path | str) -> list[DerivedArtifact]:
    """Read the derived-artifacts registry (empty list if absent). Symmetric with append_derived."""
    target = Path(run_root) / "evidence" / "derived_artifacts.json"
    if not target.is_file():
        return []
    data = json.loads(target.read_text(encoding="utf-8"))
    return [DerivedArtifact(**record) for record in data.get("derived", [])]
