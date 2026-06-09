"""EVTX tools (D5) — Security + PowerShell event log parsing (real, in-process).

Both wrap ``evtx`` (pyevtx-rs) via the backend's ``parse_evtx``. ``parse_evtx_security``
returns every Security-channel record; ``parse_evtx_powershell`` filters to the
script-block / module-logging event IDs (4103/4104) on the PowerShell-Operational
log. Each call lands a provenance line in ``audit/tool_calls.jsonl``.
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

SECURITY_CHANNELS: frozenset[str] = frozenset({"Security"})
POWERSHELL_CHANNELS: frozenset[str] = frozenset({"Microsoft-Windows-PowerShell/Operational"})

# PowerShell script-block (4104) + module logging (4103) — the high-signal IDs.
POWERSHELL_EVENT_IDS: frozenset[int] = frozenset({4103, 4104})


class EvtxParseResult(ToolResult):
    """Parsed EVTX records (normalized rows: event_id, channel, timestamp, data)."""

    event_count: int = 0
    events: list[dict[str, Any]] = Field(default_factory=list)


def _parse_evtx(
    run_root: Path | str,
    *,
    tool_name: str,
    source_artifact: str,
    evidence_root: Path | str,
    backend_mode: str | None,
    event_id_filter: frozenset[int] | None,
    channel_filter: frozenset[str] | None,
) -> EvtxParseResult:
    backend = get_backend(backend_mode)
    path, sha = resolved_source(evidence_root, source_artifact, run_root=run_root)

    def produce() -> dict[str, Any]:
        try:
            rows = backend.parse_evtx(
                path, event_id_filter=event_id_filter, channel_filter=channel_filter
            )
        except BackendUnavailableError:
            raise
        except Exception as exc:  # real parse failure -> recoverable (logged status=error)
            raise RecoverableToolError(f"evtx parse failed: {exc}", code="parse_error") from exc
        return {"event_count": len(rows), "events": rows}

    return run_tool(
        run_root,
        result_cls=EvtxParseResult,
        tool_name=tool_name,
        source_artifact=source_artifact,
        source_sha256=sha,
        backend=backend.name,
        tool_version=__version__,
        produce=produce,
        evidence_root=evidence_root,
    )


def parse_evtx_security(
    run_root: Path | str,
    *,
    source_artifact: str,
    evidence_root: Path | str,
    backend_mode: str | None = None,
) -> EvtxParseResult:
    """Parse every Security-channel record from a ``.evtx`` artifact."""
    return _parse_evtx(
        run_root,
        tool_name="parse_evtx_security",
        source_artifact=source_artifact,
        evidence_root=evidence_root,
        backend_mode=backend_mode,
        event_id_filter=None,
        channel_filter=SECURITY_CHANNELS,
    )


def parse_evtx_powershell(
    run_root: Path | str,
    *,
    source_artifact: str,
    evidence_root: Path | str,
    backend_mode: str | None = None,
) -> EvtxParseResult:
    """Parse PowerShell script-block / module-logging events (4103/4104)."""
    return _parse_evtx(
        run_root,
        tool_name="parse_evtx_powershell",
        source_artifact=source_artifact,
        evidence_root=evidence_root,
        backend_mode=backend_mode,
        event_id_filter=POWERSHELL_EVENT_IDS,
        channel_filter=POWERSHELL_CHANNELS,
    )
