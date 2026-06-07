"""Registry tool (D7) — autostart Run/RunOnce keys (real, in-process, real-on-both).

Wraps ``regipy`` via the backend's ``extract_run_keys`` over an offline registry
hive (NTUSER.DAT for HKCU, SOFTWARE for HKLM). Pure-Python; works identically on the
real and SIFT-lane backends. Logs a provenance line in ``audit/tool_calls.jsonl``.
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


class RunKeysResult(ToolResult):
    """Autostart entries extracted from Run/RunOnce keys of a registry hive."""

    run_key_count: int = 0
    run_keys: list[dict[str, Any]] = Field(default_factory=list)


def extract_registry_run_keys(
    run_root: Path | str,
    *,
    source_artifact: str,
    evidence_root: Path | str,
    backend_mode: str = "real",
) -> RunKeysResult:
    """Extract Run/RunOnce autostart entries from an offline registry hive."""
    backend = get_backend(backend_mode)
    path, sha = resolved_source(evidence_root, source_artifact)

    def produce() -> dict[str, Any]:
        try:
            rows = backend.extract_run_keys(path)
        except BackendUnavailableError:
            raise
        except Exception as exc:  # real parse failure -> recoverable (logged status=error)
            raise RecoverableToolError(f"registry parse failed: {exc}", code="parse_error") from exc
        return {"run_key_count": len(rows), "run_keys": rows}

    return run_tool(
        run_root,
        result_cls=RunKeysResult,
        tool_name="extract_registry_run_keys",
        source_artifact=source_artifact,
        source_sha256=sha,
        backend=backend.name,
        tool_version=__version__,
        produce=produce,
        evidence_root=evidence_root,
    )
