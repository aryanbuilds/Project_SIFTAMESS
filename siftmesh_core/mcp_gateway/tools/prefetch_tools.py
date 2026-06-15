"""Prefetch tool (D6) - Windows .pf execution evidence (real, in-process).

Wraps ``pyscca`` (libscca) via the backend's ``analyze_prefetch``: executable name,
run count, last-run timestamps, and referenced volumes/filenames. Logs a provenance
line in ``audit/tool_calls.jsonl``.
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


class PrefetchResult(ToolResult):
    """Parsed prefetch evidence for one ``.pf`` artifact."""

    executable_filename: str | None = None
    run_count: int | None = None
    prefetch_hash: int | None = None
    last_run_times: list[str] = Field(default_factory=list)
    volumes: list[dict[str, Any]] = Field(default_factory=list)
    filenames: list[str] = Field(default_factory=list)


def analyze_prefetch(
    run_root: Path | str,
    *,
    source_artifact: str,
    evidence_root: Path | str,
    backend_mode: str | None = None,
) -> PrefetchResult:
    """Parse a Windows prefetch (``.pf``) artifact for execution evidence."""
    backend = get_backend(backend_mode)
    path, sha = resolved_source(evidence_root, source_artifact, run_root=run_root)

    def produce() -> dict[str, Any]:
        try:
            return backend.analyze_prefetch(path)
        except BackendUnavailableError:
            raise
        except Exception as exc:  # real parse failure -> recoverable (logged status=error)
            raise RecoverableToolError(f"prefetch parse failed: {exc}", code="parse_error") from exc

    return run_tool(
        run_root,
        result_cls=PrefetchResult,
        tool_name="analyze_prefetch",
        source_artifact=source_artifact,
        source_sha256=sha,
        backend=backend.name,
        tool_version=__version__,
        produce=produce,
        evidence_root=evidence_root,
    )
