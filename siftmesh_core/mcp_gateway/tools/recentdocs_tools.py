"""RecentDocs MRU tool - files the user recently opened (NTUSER.DAT, real, in-process).

Wraps ``regipy`` via the backend's ``extract_recentdocs`` to surface the HKCU RecentDocs MRU (and
its per-extension subkeys): the decoded filenames the user opened, with the key's last-write time.
Direct evidence of "what key projects/files Fred opened" (Q1) and a candidate set for "what was
taken" (Q2). Logs provenance to ``audit/tool_calls.jsonl``.
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


class RecentDocsResult(ToolResult):
    """Parsed RecentDocs MRU entries for one NTUSER.DAT hive."""

    entry_count: int = 0
    mru_entries: list[dict[str, Any]] = Field(default_factory=list)


def parse_recentdocs_mru(
    run_root: Path | str,
    *,
    source_artifact: str,
    evidence_root: Path | str,
    backend_mode: str | None = None,
) -> RecentDocsResult:
    """Extract RecentDocs MRU (recently-opened files) from an NTUSER.DAT registry hive."""
    backend = get_backend(backend_mode)
    path, sha = resolved_source(evidence_root, source_artifact, run_root=run_root)

    def produce() -> dict[str, Any]:
        try:
            rows = backend.extract_recentdocs(path)
        except BackendUnavailableError:
            raise
        except Exception as exc:  # real parse failure -> recoverable (logged status=error)
            raise RecoverableToolError(
                f"recentdocs parse failed: {exc}", code="parse_error"
            ) from exc
        return {"entry_count": len(rows), "mru_entries": rows}

    return run_tool(
        run_root,
        result_cls=RecentDocsResult,
        tool_name="parse_recentdocs_mru",
        source_artifact=source_artifact,
        source_sha256=sha,
        backend=backend.name,
        tool_version=__version__,
        produce=produce,
        evidence_root=evidence_root,
    )
