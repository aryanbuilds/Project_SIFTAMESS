"""Shellbags tool — folder-access history from BagMRU (real, in-process).

Wraps ``regipy``'s shellbag plugins (PIDL decode via ``libfwsi`` + ``libfwps``) via the backend's
``extract_shellbags``. Shellbags survive in ``UsrClass.dat`` (and a ``NTUSER`` BagMRU) and record
folders the user browsed in Explorer — including paths that no longer exist on disk — direct
evidence of "where files were / where they were staged" (Q1/Q3/Q5). A missing decoder lib fails
closed; folder names are never fabricated. Logs provenance to ``audit/tool_calls.jsonl``.
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


class ShellbagResult(ToolResult):
    """Parsed shellbag (BagMRU) folder-access entries for one registry hive."""

    entry_count: int = 0
    entries: list[dict[str, Any]] = Field(default_factory=list)


def parse_shellbags(
    run_root: Path | str,
    *,
    source_artifact: str,
    evidence_root: Path | str,
    backend_mode: str | None = None,
) -> ShellbagResult:
    """Extract shellbags (BagMRU folder-access history) from a UsrClass.dat / NTUSER hive."""
    backend = get_backend(backend_mode)
    path, sha = resolved_source(evidence_root, source_artifact, run_root=run_root)

    def produce() -> dict[str, Any]:
        try:
            rows = backend.extract_shellbags(path)
        except BackendUnavailableError:
            raise
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
