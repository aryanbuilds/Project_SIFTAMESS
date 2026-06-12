"""USB / removable-media registry tool — exfil-channel evidence (real, in-process).

Wraps ``regipy`` via the backend's ``extract_usb_devices`` to surface USBSTOR device enumeration
(SYSTEM hive, active control set) and MountPoints2 (NTUSER.DAT) — removable drives + mounted
volumes/UNC shares the host saw. A candidate "where transferred / how" (Q3/Q4) and "when" (Q5,
device last-write) signal. Attachment is NOT proof of transfer; the claim layer keeps that inferred.
Logs provenance to ``audit/tool_calls.jsonl``.
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


class UsbRegistryResult(ToolResult):
    """Parsed removable-media registry evidence for one SYSTEM or NTUSER hive."""

    device_count: int = 0
    devices: list[dict[str, Any]] = Field(default_factory=list)


def parse_usb_registry(
    run_root: Path | str,
    *,
    source_artifact: str,
    evidence_root: Path | str,
    backend_mode: str | None = None,
) -> UsbRegistryResult:
    """Extract USBSTOR (SYSTEM) + MountPoints2 (NTUSER) removable-media evidence from a hive."""
    backend = get_backend(backend_mode)
    path, sha = resolved_source(evidence_root, source_artifact, run_root=run_root)

    def produce() -> dict[str, Any]:
        try:
            rows = backend.extract_usb_devices(path)
        except BackendUnavailableError:
            raise
        except Exception as exc:  # real parse failure -> recoverable (logged status=error)
            raise RecoverableToolError(
                f"usb registry parse failed: {exc}", code="parse_error"
            ) from exc
        return {"device_count": len(rows), "devices": rows}

    return run_tool(
        run_root,
        result_cls=UsbRegistryResult,
        tool_name="parse_usb_registry",
        source_artifact=source_artifact,
        source_sha256=sha,
        backend=backend.name,
        tool_version=__version__,
        produce=produce,
        evidence_root=evidence_root,
    )
