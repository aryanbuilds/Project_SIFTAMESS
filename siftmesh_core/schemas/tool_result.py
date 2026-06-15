"""Tool-result provenance base (C1, design rule D1).

``ToolResult`` is the single provenance base that every typed forensic tool
return subclasses (Epic D). It carries the chain-of-custody fields CLAUDE.md §7
requires on *every* tool output, so they are never re-enumerated per tool. Types
only - the audited execution that populates these fields lands in Epic D.
"""

from __future__ import annotations

from typing import Literal

from siftmesh_core.schemas._base import Sha256, StrictModel, UtcDateTime

ToolStatus = Literal["success", "error", "timeout"]


class ToolResult(StrictModel):
    """Provenance every tool return carries (subclass to add structured rows)."""

    tool_call_id: str
    tool_name: str
    source_artifact: str
    source_sha256: Sha256
    start_time_utc: UtcDateTime
    end_time_utc: UtcDateTime
    status: ToolStatus
    backend: str
    tool_version: str
    structured_result_path: str | None = None
    raw_output_path: str | None = None
    error_code: str | None = None
