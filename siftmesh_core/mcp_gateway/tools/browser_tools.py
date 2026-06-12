"""Browser history parsing tool."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import Field

from siftmesh_core import __version__
from siftmesh_core.mcp_gateway.audit_exec import RecoverableToolError, run_tool
from siftmesh_core.mcp_gateway.backends import get_backend
from siftmesh_core.mcp_gateway.tools._common import resolved_source
from siftmesh_core.schemas.tool_result import ToolResult


class BrowserHistoryResult(ToolResult):
    entry_count: int = 0
    visit_count: int = 0
    download_count: int = 0
    history: list[dict[str, Any]] = Field(default_factory=list)


def parse_browser_history(
    run_root: Path | str,
    *,
    source_artifact: str,
    evidence_root: Path | str,
    backend_mode: str | None = None,
) -> BrowserHistoryResult:
    backend = get_backend(backend_mode)
    path, sha = resolved_source(evidence_root, source_artifact, run_root=run_root)

    def produce() -> dict[str, Any]:
        try:
            rows = backend.parse_browser_history(path)
        except Exception as exc:  # real parse failure -> recoverable (logged status=error)
            raise RecoverableToolError(
                f"browser history parse failed: {exc}", code="parse_error"
            ) from exc
        visits = sum(1 for r in rows if r.get("kind") == "visit")
        downloads = sum(1 for r in rows if r.get("kind") == "download")
        return {
            "entry_count": len(rows),
            "visit_count": visits,
            "download_count": downloads,
            "history": rows,
        }

    return run_tool(
        run_root,
        result_cls=BrowserHistoryResult,
        tool_name="parse_browser_history",
        source_artifact=source_artifact,
        source_sha256=sha,
        backend=backend.name,
        tool_version=__version__,
        produce=produce,
        evidence_root=evidence_root,
    )
