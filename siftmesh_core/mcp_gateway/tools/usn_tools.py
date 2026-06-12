"""USN journal tool — file create/delete/rename change log (real, in-process).

Wraps the in-process ``USN_RECORD_V2`` reader (backend ``parse_usnjrnl``) over the
``$Extend\\$UsnJrnl:$J`` change journal. The USN journal records every file create / delete /
rename / data-change with a timestamp — including files that were **deleted** and no longer exist
on disk — so it is direct evidence for "what was created/taken/removed and when" (Q2/Q5). Logs
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


class UsnJournalResult(ToolResult):
    """Parsed USN journal change records for one ``$J`` stream."""

    entry_count: int = 0
    entries: list[dict[str, Any]] = Field(default_factory=list)


def parse_usnjrnl(
    run_root: Path | str,
    *,
    source_artifact: str,
    evidence_root: Path | str,
    backend_mode: str | None = None,
) -> UsnJournalResult:
    """Parse a USN change journal (``$Extend\\$UsnJrnl:$J``) stream."""
    backend = get_backend(backend_mode)
    path, sha = resolved_source(evidence_root, source_artifact, run_root=run_root)

    def produce() -> dict[str, Any]:
        try:
            rows = backend.parse_usnjrnl(path)
        except BackendUnavailableError:
            raise
        except Exception as exc:  # real parse failure -> recoverable (logged status=error)
            raise RecoverableToolError(
                f"usn journal parse failed: {exc}", code="parse_error"
            ) from exc
        return {"entry_count": len(rows), "entries": rows}

    return run_tool(
        run_root,
        result_cls=UsnJournalResult,
        tool_name="parse_usnjrnl",
        source_artifact=source_artifact,
        source_sha256=sha,
        backend=backend.name,
        tool_version=__version__,
        produce=produce,
        evidence_root=evidence_root,
    )
