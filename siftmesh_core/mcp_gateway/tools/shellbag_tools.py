"""Shellbags tool for parsing BagMRU folder-access history."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import Field

from siftmesh_core import __version__
from siftmesh_core.mcp_gateway.audit_exec import RecoverableToolError, run_tool
from siftmesh_core.mcp_gateway.backends import get_backend
from siftmesh_core.mcp_gateway.tools._common import resolved_source
from siftmesh_core.schemas.tool_result import ToolResult


class ShellbagResult(ToolResult):
    entry_count: int = 0
    entries: list[dict[str, Any]] = Field(default_factory=list)


def parse_shellbags(
    run_root: Path | str,
    *,
    source_artifact: str,
    evidence_root: Path | str,
    backend_mode: str | None = None,
) -> ShellbagResult:
    backend = get_backend(backend_mode)
    path, sha = resolved_source(evidence_root, source_artifact, run_root=run_root)

    def produce() -> dict[str, Any]:
        try:
            rows = backend.extract_shellbags(path)
        except Exception as exc:  # real parse failure -> recoverable (logged status=error)
            raise RecoverableToolError(f"shellbag parse failed: {exc}", code="parse_error") from exc
        return {"entry_count": len(rows), "entries": rows}

    return run_tool(
        run_root,
        result_cls=ShellbagResult,
        tool_name="parse_shellbags",
        source_artifact=source_artifact,
        source_sha256=sha,
        backend=backend.name,
        tool_version=__version__,
        produce=produce,
        evidence_root=evidence_root,
    )
