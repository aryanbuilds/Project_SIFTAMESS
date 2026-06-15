"""MFT filesystem tool - NTFS ``$MFT`` file inventory + timestamps (real, in-process).

Wraps ``mft`` (pymft-rs) via the backend's existing ``parse_mft`` to expose a standalone filesystem
listing: per-entry filename, logical size, directory flag, and ``$STANDARD_INFORMATION``
created/modified/accessed times - answering "what files existed/were staged" (Q2) + the "when" (Q5).
The same rows also feed ``build_timeline`` (kind=mft); this surfaces them as their own anchored
result. Provenance is logged to ``audit/tool_calls.jsonl``.

Note: pymft-rs does not reconstruct full parent paths, so rows carry the entry name + metadata (not
an absolute path); ``$STANDARD_INFORMATION`` times are timestomp-prone (claims treat them inferred).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import Field

from siftmesh_core import __version__
from siftmesh_core.mcp_gateway.audit_exec import RecoverableToolError, run_tool
from siftmesh_core.mcp_gateway.backends import BackendUnavailableError, get_backend
from siftmesh_core.mcp_gateway.tools._common import resolved_source
from siftmesh_core.schemas.tool_result import ToolResult


class MftFilesystemResult(ToolResult):
    """Parsed ``$MFT`` filesystem metadata for one Master File Table."""

    entry_count: int = 0
    file_count: int = 0
    directory_count: int = 0
    files: list[dict[str, Any]] = Field(default_factory=list)


def parse_mft_filesystem(
    run_root: Path | str,
    *,
    source_artifact: str,
    evidence_root: Path | str,
    backend_mode: str | None = None,
) -> MftFilesystemResult:
    """Parse an NTFS ``$MFT`` into a filesystem inventory (names, sizes, timestamps)."""
    backend = get_backend(backend_mode)
    path, sha = resolved_source(evidence_root, source_artifact, run_root=run_root)

    def produce() -> dict[str, Any]:
        try:
            rows = backend.parse_mft(path)
        except BackendUnavailableError:
            raise
        except Exception as exc:  # real parse failure -> recoverable (logged status=error)
            raise RecoverableToolError(f"mft parse failed: {exc}", code="parse_error") from exc
        directory_count = sum(1 for r in rows if r.get("is_directory"))
        return {
            "entry_count": len(rows),
            "file_count": len(rows) - directory_count,
            "directory_count": directory_count,
            "files": rows,
        }

    return run_tool(
        run_root,
        result_cls=MftFilesystemResult,
        tool_name="parse_mft_filesystem",
        source_artifact=source_artifact,
        source_sha256=sha,
        backend=backend.name,
        tool_version=__version__,
        produce=produce,
        evidence_root=evidence_root,
    )
