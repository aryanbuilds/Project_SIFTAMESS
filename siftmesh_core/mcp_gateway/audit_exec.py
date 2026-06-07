"""Audited tool execution (D2) — the provenance keystone.

Every typed tool runs through :func:`run_tool`: it allocates a deterministic
``TOOL-NNN`` id, stamps UTC start/end, runs the producer, writes the structured
result under the run dir (path-policed), registers the derived artifact + a
``tool_invoked`` custody event, and appends exactly one fully-populated
``ToolResult`` line to ``audit/tool_calls.jsonl`` — on success AND on failure
(criterion 5: every call is traceable). No tool bypasses this.

A recoverable failure is logged as ``status=error`` and returned (the orchestrator
decides retry). A missing backend (:class:`BackendUnavailableError`) is logged then
re-raised — it fails closed rather than yielding a fake result.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypeVar

from siftmesh_core import __version__
from siftmesh_core.evidence.derived import DerivedArtifact, append_derived
from siftmesh_core.evidence.hash_utils import sha256_file
from siftmesh_core.evidence.path_policy import safe_write_path
from siftmesh_core.ledgers.custody_ledger import append_event
from siftmesh_core.ledgers.tool_call_ledger import append_tool_result, read_tool_results
from siftmesh_core.mcp_gateway.backends import BackendUnavailableError
from siftmesh_core.schemas.custody import CustodyEvent
from siftmesh_core.schemas.tool_result import ToolResult, ToolStatus

ToolResultT = TypeVar("ToolResultT", bound=ToolResult)


class RecoverableToolError(RuntimeError):
    """A recoverable tool failure (logged as status=error; orchestrator may retry)."""

    def __init__(self, message: str, *, code: str = "tool_error") -> None:
        super().__init__(message)
        self.code = code


def _next_tool_call_id(run_root: Path | str) -> str:
    """Allocate the next deterministic ``TOOL-NNN`` id from the ledger length."""
    return f"TOOL-{len(read_tool_results(run_root)) + 1:03d}"


def _write_structured(
    run_root: Path | str,
    tool_call_id: str,
    payload: dict[str, Any],
    *,
    evidence_root: Path | str | None,
) -> str:
    """Write the structured result JSON under ``results/`` (path-policed)."""
    rel = Path("results") / f"{tool_call_id}.structured.json"
    target = safe_write_path(run_root, rel, evidence_root=evidence_root)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    return rel.as_posix()


def run_tool(
    run_root: Path | str,
    *,
    result_cls: type[ToolResultT],
    tool_name: str,
    source_artifact: str,
    source_sha256: str,
    backend: str,
    produce: Callable[[], dict[str, Any]],
    tool_version: str = __version__,
    evidence_root: Path | str | None = None,
    write_structured: bool = True,
) -> ToolResultT:
    """Run ``produce`` with full provenance; append one ``tool_calls.jsonl`` line.

    ``produce`` returns the structured payload (the ``result_cls`` extra fields).
    On success the payload is written + merged into the typed result; on a
    recoverable error an empty ``status=error`` result is logged and returned.
    """
    tool_call_id = _next_tool_call_id(run_root)
    start = datetime.now(UTC)
    status: ToolStatus = "success"
    error_code: str | None = None
    payload: dict[str, Any] = {}
    reraise: Exception | None = None
    try:
        payload = produce()
    except BackendUnavailableError as exc:
        status, error_code, reraise = "error", "backend_unavailable", exc
    except RecoverableToolError as exc:
        status, error_code = "error", exc.code
    end = datetime.now(UTC)

    structured_path: str | None = (
        (Path("results") / f"{tool_call_id}.structured.json").as_posix()
        if status == "success" and write_structured
        else None
    )

    # Provenance (base ToolResult) is what lands in audit/tool_calls.jsonl; the
    # structured payload lives in the structured_result_path file it points to.
    provenance: dict[str, Any] = {
        "tool_call_id": tool_call_id,
        "tool_name": tool_name,
        "source_artifact": source_artifact,
        "source_sha256": source_sha256,
        "start_time_utc": start,
        "end_time_utc": end,
        "status": status,
        "backend": backend,
        "tool_version": tool_version,
        "structured_result_path": structured_path,
        "error_code": error_code,
    }
    result = result_cls(**provenance, **(payload if status == "success" else {}))

    if structured_path is not None:
        _write_structured(run_root, tool_call_id, payload, evidence_root=evidence_root)

    append_tool_result(run_root, ToolResult(**provenance), evidence_root=evidence_root)

    append_event(
        run_root,
        CustodyEvent(
            event_type="tool_invoked",
            run_id=Path(run_root).resolve().name,
            artifact=source_artifact,
            source_sha256=source_sha256,
            action=tool_name,
            actor="siftmesh",
            tool_name=tool_name,
            tool_version=tool_version,
            start_time_utc=start,
            end_time_utc=end,
            result=status,
        ),
        evidence_root=evidence_root,
    )

    if structured_path is not None:
        written = safe_write_path(run_root, structured_path, evidence_root=evidence_root)
        append_derived(
            run_root,
            DerivedArtifact(
                derived_path=structured_path,
                source_artifact=source_artifact,
                source_sha256=source_sha256,
                tool_call_id=tool_call_id,
                derived_sha256=sha256_file(written),
            ),
            evidence_root=evidence_root,
        )

    if reraise is not None:
        raise reraise
    return result
