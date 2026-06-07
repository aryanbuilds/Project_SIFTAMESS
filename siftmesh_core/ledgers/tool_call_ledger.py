"""Tool-call audit ledger (C7): every executed tool call's provenance.

Appends a :class:`ToolResult` (the provenance CLAUDE.md §7 mandates for every
tool output) to ``audit/tool_calls.jsonl``. The audited-execution wrapper that
*calls* this on every tool run is Epic D — here we provide the typed ledger it
will use, built on the generic validate-before-write JSONL ledger.
"""

from __future__ import annotations

from pathlib import Path

from siftmesh_core.ledgers.jsonl_ledger import append_record, read_records
from siftmesh_core.schemas.tool_result import ToolResult

_TOOL_CALLS = Path("audit") / "tool_calls.jsonl"


def append_tool_result(
    run_root: Path | str,
    result: ToolResult,
    *,
    evidence_root: Path | str | None = None,
) -> Path:
    """Append one tool-call provenance record to ``audit/tool_calls.jsonl``."""
    return append_record(run_root, _TOOL_CALLS, result, evidence_root=evidence_root)


def read_tool_results(run_root: Path | str) -> list[ToolResult]:
    """Read all tool-call provenance records for a run."""
    return list(read_records(Path(run_root) / _TOOL_CALLS, ToolResult))
