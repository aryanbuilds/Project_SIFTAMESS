"""Browser-history tool — visited URLs + downloads (Chromium / Firefox, real, in-process).

Wraps stdlib ``sqlite3`` via the backend's ``parse_browser_history`` to surface a user's web
activity from a Chromium ``History`` DB (Chrome/Edge ``urls`` + ``downloads``) or a Firefox
``places.sqlite`` (``moz_places`` + download annotations). The DB is opened read-only/immutable
over a temp copy, so the original evidence is never touched. Download target paths + visited
cloud-storage domains are direct leads for "what was taken / where it went" (Q2/Q3/Q4/Q5). Logs
provenance to ``audit/tool_calls.jsonl``.
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


class BrowserHistoryResult(ToolResult):
    """Parsed browser history (visits + downloads) for one history database."""

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
    """Parse a browser history database (Chromium ``History`` or Firefox ``places.sqlite``)."""
    backend = get_backend(backend_mode)
    path, sha = resolved_source(evidence_root, source_artifact, run_root=run_root)

    def produce() -> dict[str, Any]:
        try:
            rows = backend.parse_browser_history(path)
        except BackendUnavailableError:
            raise
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
