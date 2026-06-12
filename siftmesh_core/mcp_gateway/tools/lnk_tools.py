"""LNK / JumpList tool — shortcuts + recent-item destinations (real, in-process).

Wraps ``LnkParse3`` (+ ``olefile`` for AutomaticDestinations OLE compounds) via the backend's
``parse_lnk_jumplists``. One tool covers ``.lnk`` files and both JumpList kinds
(``*.automaticDestinations-ms`` / ``*.customDestinations-ms``); every row is tagged
``kind=lnk|jumplist`` with the resolved target path. LNK/JumpList target paths are direct
evidence of "what files the user opened / where they lived" (Q1/Q2/Q3). Logs provenance to
``audit/tool_calls.jsonl``.
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


class LnkJumplistResult(ToolResult):
    """Parsed LNK / JumpList entries for one shortcut or destinations file."""

    entry_count: int = 0
    lnk_count: int = 0
    jumplist_count: int = 0
    entries: list[dict[str, Any]] = Field(default_factory=list)


def parse_lnk_jumplists(
    run_root: Path | str,
    *,
    source_artifact: str,
    evidence_root: Path | str,
    backend_mode: str | None = None,
) -> LnkJumplistResult:
    """Parse a ``.lnk`` shortcut or a JumpList (Auto/Custom Destinations) file."""
    backend = get_backend(backend_mode)
    path, sha = resolved_source(evidence_root, source_artifact, run_root=run_root)

    def produce() -> dict[str, Any]:
        try:
            rows = backend.parse_lnk_jumplists(path)
        except BackendUnavailableError:
            raise
        except Exception as exc:  # real parse failure -> recoverable (logged status=error)
            raise RecoverableToolError(
                f"lnk/jumplist parse failed: {exc}", code="parse_error"
            ) from exc
        lnks = sum(1 for r in rows if r.get("kind") == "lnk")
        jumps = sum(1 for r in rows if r.get("kind") == "jumplist")
        return {
            "entry_count": len(rows),
            "lnk_count": lnks,
            "jumplist_count": jumps,
            "entries": rows,
        }

    return run_tool(
        run_root,
        result_cls=LnkJumplistResult,
        tool_name="parse_lnk_jumplists",
        source_artifact=source_artifact,
        source_sha256=sha,
        backend=backend.name,
        tool_version=__version__,
        produce=produce,
        evidence_root=evidence_root,
    )
