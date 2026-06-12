from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import Field

from siftmesh_core import __version__
from siftmesh_core.mcp_gateway.audit_exec import RecoverableToolError, run_tool
from siftmesh_core.mcp_gateway.backends import get_backend
from siftmesh_core.mcp_gateway.tools._common import resolved_source
from siftmesh_core.schemas.tool_result import ToolResult


class AmcacheShimcacheResult(ToolResult):
    entry_count: int = 0
    amcache_count: int = 0
    shimcache_count: int = 0
    entries: list[dict[str, Any]] = Field(default_factory=list)


def parse_amcache_shimcache(
    run_root: Path | str,
    *,
    source_artifact: str,
    evidence_root: Path | str,
    backend_mode: str | None = None,
) -> AmcacheShimcacheResult:
    backend = get_backend(backend_mode)
    path, sha = resolved_source(evidence_root, source_artifact, run_root=run_root)

    def produce() -> dict[str, Any]:
        try:
            rows = backend.extract_amcache_shimcache(path)
        except Exception as exc:
            raise RecoverableToolError(
                f"amcache/shimcache parse failed: {exc}", code="parse_error"
            ) from exc
        amcache = sum(1 for r in rows if r.get("kind") == "amcache")
        shimcache = sum(1 for r in rows if r.get("kind") == "shimcache")
        return {
            "entry_count": len(rows),
            "amcache_count": amcache,
            "shimcache_count": shimcache,
            "entries": rows,
        }

    return run_tool(
        run_root,
        result_cls=AmcacheShimcacheResult,
        tool_name="parse_amcache_shimcache",
        source_artifact=source_artifact,
        source_sha256=sha,
        backend=backend.name,
        tool_version=__version__,
        produce=produce,
        evidence_root=evidence_root,
    )
