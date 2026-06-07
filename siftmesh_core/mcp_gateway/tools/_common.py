"""Shared helpers for the parser tools (D5-D8).

Resolves an evidence-relative artifact to a real file *inside* the evidence tree
(rejecting traversal — case data is hostile, CLAUDE.md §6) and hashes the exact
bytes the tool is about to parse (a real per-access integrity hash that becomes the
``source_sha256`` provenance).
"""

from __future__ import annotations

from pathlib import Path

from siftmesh_core.evidence.hash_utils import sha256_file


def resolved_source(evidence_root: Path | str, source_artifact: str) -> tuple[Path, str]:
    """Return ``(real_path, sha256)`` for an artifact, or raise if missing/escaping."""
    root = Path(evidence_root).resolve()
    path = (root / source_artifact).resolve()
    if not path.is_relative_to(root):
        raise ValueError(f"artifact escapes evidence root: {source_artifact!r}")
    if not path.is_file():
        raise FileNotFoundError(f"source artifact not found: {source_artifact}")
    return path, sha256_file(path)
