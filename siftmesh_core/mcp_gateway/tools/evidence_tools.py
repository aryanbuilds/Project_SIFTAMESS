"""Evidence tools (D4) — always-real, pure-stdlib.

``compute_hash_manifest`` and ``create_readonly_evidence_vault`` wrap the Epic B
evidence primitives (streaming SHA-256 walk, read-only posture) and run through the
audited-execution wrapper so each call lands a provenance line in
``audit/tool_calls.jsonl``. No external library, no subprocess.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from pydantic import Field

from siftmesh_core import __version__
from siftmesh_core.evidence.hash_utils import FileFact, walk_files
from siftmesh_core.evidence.readonly import write_readonly_record
from siftmesh_core.mcp_gateway.audit_exec import run_tool
from siftmesh_core.schemas.tool_result import ToolResult


class HashManifestResult(ToolResult):
    """``compute_hash_manifest`` output: per-file hashes + a manifest digest."""

    file_count: int = 0
    files: list[dict[str, Any]] = Field(default_factory=list)
    manifest_sha256: str | None = None


class ReadonlyVaultResult(ToolResult):
    """``create_readonly_evidence_vault`` output: the recorded read-only posture."""

    evidence_root: str | None = None
    file_count: int = 0
    enforcement: str | None = None


def _facts_digest(facts: list[FileFact]) -> str:
    """A stable digest over the sorted ``<hash>  <relpath>`` lines (manifest hash)."""
    blob = "".join(f"{fact.sha256}  {fact.rel_path}\n" for fact in facts)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def compute_hash_manifest(
    run_root: Path | str,
    *,
    evidence_root: Path | str,
    backend_mode: str = "real",
) -> HashManifestResult:
    """Hash every file under ``evidence_root`` and log a manifest provenance record."""
    facts = walk_files(evidence_root)
    digest = _facts_digest(facts)

    def produce() -> dict[str, Any]:
        return {
            "file_count": len(facts),
            "files": [
                {"path": f.rel_path, "sha256": f.sha256, "size_bytes": f.size_bytes} for f in facts
            ],
            "manifest_sha256": digest,
        }

    return run_tool(
        run_root,
        result_cls=HashManifestResult,
        tool_name="compute_hash_manifest",
        source_artifact=".",
        source_sha256=digest,
        backend="real",
        tool_version=__version__,
        produce=produce,
        evidence_root=evidence_root,
    )


def create_readonly_evidence_vault(
    run_root: Path | str,
    *,
    evidence_root: Path | str,
    backend_mode: str = "real",
) -> ReadonlyVaultResult:
    """Record the read-only evidence posture and log a provenance record."""
    facts = walk_files(evidence_root)
    digest = _facts_digest(facts)
    write_readonly_record(evidence_root, run_root, file_count=len(facts))
    resolved = str(Path(evidence_root).resolve())

    def produce() -> dict[str, Any]:
        return {
            "evidence_root": resolved,
            "file_count": len(facts),
            "enforcement": "posture_only",
        }

    return run_tool(
        run_root,
        result_cls=ReadonlyVaultResult,
        tool_name="create_readonly_evidence_vault",
        source_artifact=".",
        source_sha256=digest,
        backend="real",
        tool_version=__version__,
        produce=produce,
        evidence_root=evidence_root,
    )
