"""Image extraction tool (Epic D deepening) — pull loose artifacts out of a disk image.

``extract_artifacts_from_image`` runs The Sleuth Kit (SIFT-lane, fixed-argv) over an
``.E01``/raw image to extract the high-value Windows artifacts into
``run/evidence/extracted/``, then registers each as a :class:`DerivedArtifact` with full
provenance (source image + sha + NTFS path + TSK inode). The call itself is audited via
``run_tool`` (one ``tool_calls.jsonl`` line, custody + derived records). The extracted loose
files become the inputs the existing in-process parsers consume.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import Field

from siftmesh_core import __version__
from siftmesh_core.evidence import image_access
from siftmesh_core.evidence.derived import DerivedArtifact, append_derived
from siftmesh_core.evidence.path_policy import safe_write_path
from siftmesh_core.mcp_gateway.audit_exec import RecoverableToolError, run_tool
from siftmesh_core.mcp_gateway.backends import BackendUnavailableError
from siftmesh_core.mcp_gateway.tools._common import resolved_source
from siftmesh_core.schemas.tool_result import ToolResult

# Where extracted artifacts land under the run dir (path-policed).
_EXTRACT_SUBDIR = Path("evidence") / "extracted"


class ImageExtractionResult(ToolResult):
    """Artifacts extracted from a disk image, with per-file provenance."""

    partition_offset: int = 0
    partition_count: int = 0
    extracted_count: int = 0
    extracted: list[dict[str, Any]] = Field(default_factory=list)


def extract_artifacts_from_image(
    run_root: Path | str,
    *,
    image_artifact: str,
    evidence_root: Path | str,
    keys: list[str] | None = None,
    backend_mode: str = "sift_lane",
) -> ImageExtractionResult:
    """Extract curated Windows artifacts from ``image_artifact`` (an ``.E01``/raw image).

    ``image_artifact`` is evidence-relative; ``keys`` optionally restricts to a subset of
    ``image_access.ARTIFACT_MAP`` keys. Extracted files are written under
    ``run/evidence/extracted/`` and each is registered as a derived artifact.
    """
    image_path, image_sha = resolved_source(evidence_root, image_artifact)
    run_root_resolved = Path(run_root).resolve()
    dest_dir = safe_write_path(run_root, _EXTRACT_SUBDIR, evidence_root=evidence_root)
    key_filter = frozenset(keys) if keys else None
    extracted: list[image_access.ExtractedFile] = []

    def produce() -> dict[str, Any]:
        offset = image_access.resolve_offset(image_path)
        partitions = image_access.list_partitions(image_path)
        try:
            files = image_access.extract_artifacts(
                image_path, dest_dir=dest_dir, offset=offset, keys=key_filter
            )
        except BackendUnavailableError:
            raise
        except Exception as exc:  # real extraction failure -> recoverable (logged status=error)
            raise RecoverableToolError(
                f"image extraction failed: {exc}", code="extract_error"
            ) from exc
        extracted.extend(files)
        return {
            "partition_offset": offset,
            "partition_count": len(partitions),
            "extracted_count": len(files),
            "extracted": [
                {
                    "key": f.key,
                    "ntfs_path": f.ntfs_path,
                    "inode": f.inode,
                    "derived_path": f.dest.resolve().relative_to(run_root_resolved).as_posix(),
                    "sha256": f.sha256,
                    "size_bytes": f.size_bytes,
                }
                for f in files
            ],
        }

    result = run_tool(
        run_root,
        result_cls=ImageExtractionResult,
        tool_name="extract_artifacts_from_image",
        source_artifact=image_artifact,
        source_sha256=image_sha,
        backend="sift_lane",
        tool_version=__version__,
        produce=produce,
        evidence_root=evidence_root,
    )

    # Register each extracted file as a derived artifact (chain: image -> extracted file).
    if result.status == "success":
        for f in extracted:
            derived_rel = f.dest.resolve().relative_to(run_root_resolved).as_posix()
            append_derived(
                run_root,
                DerivedArtifact(
                    derived_path=derived_rel,
                    source_artifact=image_artifact,
                    source_sha256=image_sha,
                    tool_call_id=result.tool_call_id,
                    derived_sha256=f.sha256,
                    extraction_source_path=f.ntfs_path,
                    extraction_inode=f.inode,
                    extraction_method="sleuthkit_icat",
                ),
                evidence_root=evidence_root,
            )
    return result
