"""Amcache + ShimCache tool — program execution / presence (real, in-process).

Wraps ``regipy``'s ``AmCachePlugin`` (Amcache.hve) + ``ShimCachePlugin`` (SYSTEM AppCompatCache)
via the backend's ``extract_amcache_shimcache``. One tool, two sources; every row is tagged
``kind=amcache|shimcache``. Amcache records installed/run programs with SHA-1 + first-run time;
ShimCache records executables the application-compat engine saw — together strong corroboration for
"what ran / how it got there" (Q4) and "when" (Q5). Logs provenance to ``audit/tool_calls.jsonl``.
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


class AmcacheShimcacheResult(ToolResult):
    """Parsed Amcache + ShimCache program-execution entries for one registry hive."""

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
    """Extract program-execution evidence from an Amcache.hve or a SYSTEM hive (ShimCache)."""
    backend = get_backend(backend_mode)
    path, sha = resolved_source(evidence_root, source_artifact, run_root=run_root)

    def produce() -> dict[str, Any]:
        try:
            rows = backend.extract_amcache_shimcache(path)
        except BackendUnavailableError:
            raise
        except Exception as exc:  # real parse failure -> recoverable (logged status=error)
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
