"""FastMCP server (D1) — the thin agent-facing adapter over the typed tools.

Registers EXACTLY the eight allowlisted forensic tools (CLAUDE.md §7) on a FastMCP
stdio server, each guarded by :func:`assert_tool_allowed` at registration so a
forbidden / off-allowlist name can never be exposed (criterion 4). The adapters are
thin: they take primitive args an agent can supply and delegate to the same service
functions the CLI calls directly (CLI-first). Returns are ``ToolResult`` subclasses
(structured MCP output).
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from siftmesh_core.mcp_gateway.registry import ALLOWED_TOOLS, assert_tool_allowed
from siftmesh_core.mcp_gateway.tools.evidence_tools import (
    HashManifestResult,
    ReadonlyVaultResult,
    compute_hash_manifest,
    create_readonly_evidence_vault,
)
from siftmesh_core.mcp_gateway.tools.evtx_tools import (
    EvtxParseResult,
    parse_evtx_powershell,
    parse_evtx_security,
)
from siftmesh_core.mcp_gateway.tools.prefetch_tools import PrefetchResult, analyze_prefetch
from siftmesh_core.mcp_gateway.tools.registry_tools import RunKeysResult, extract_registry_run_keys
from siftmesh_core.mcp_gateway.tools.timeline_tools import TimelineResult, build_timeline
from siftmesh_core.mcp_gateway.tools.validation_tools import (
    ClaimValidationResult,
    validate_claim_evidence,
)

# ── Thin MCP adapters (primitive args -> service functions) ─────────────────


def _compute_hash_manifest(run_root: str, evidence_root: str) -> HashManifestResult:
    return compute_hash_manifest(run_root, evidence_root=evidence_root)


def _create_readonly_evidence_vault(run_root: str, evidence_root: str) -> ReadonlyVaultResult:
    return create_readonly_evidence_vault(run_root, evidence_root=evidence_root)


def _parse_evtx_security(
    run_root: str, source_artifact: str, evidence_root: str
) -> EvtxParseResult:
    return parse_evtx_security(
        run_root, source_artifact=source_artifact, evidence_root=evidence_root
    )


def _parse_evtx_powershell(
    run_root: str, source_artifact: str, evidence_root: str
) -> EvtxParseResult:
    return parse_evtx_powershell(
        run_root, source_artifact=source_artifact, evidence_root=evidence_root
    )


def _analyze_prefetch(run_root: str, source_artifact: str, evidence_root: str) -> PrefetchResult:
    return analyze_prefetch(run_root, source_artifact=source_artifact, evidence_root=evidence_root)


def _extract_registry_run_keys(
    run_root: str, source_artifact: str, evidence_root: str
) -> RunKeysResult:
    return extract_registry_run_keys(
        run_root, source_artifact=source_artifact, evidence_root=evidence_root
    )


def _build_timeline(
    run_root: str, inputs: list[dict[str, str]], evidence_root: str
) -> TimelineResult:
    return build_timeline(run_root, inputs=inputs, evidence_root=evidence_root)


def _validate_claim_evidence(
    run_root: str, claim: dict[str, Any], evidence_root: str
) -> ClaimValidationResult:
    return validate_claim_evidence(run_root, claim, evidence_root=evidence_root)


def tool_adapters() -> dict[str, Any]:
    """The allowlisted tool name -> MCP adapter mapping (the complete tool surface)."""
    return {
        "compute_hash_manifest": _compute_hash_manifest,
        "create_readonly_evidence_vault": _create_readonly_evidence_vault,
        "parse_evtx_security": _parse_evtx_security,
        "parse_evtx_powershell": _parse_evtx_powershell,
        "analyze_prefetch": _analyze_prefetch,
        "extract_registry_run_keys": _extract_registry_run_keys,
        "build_timeline": _build_timeline,
        "validate_claim_evidence": _validate_claim_evidence,
    }


def registered_tool_names(mcp: FastMCP) -> set[str]:
    """The set of tool names currently registered on a FastMCP server (sync)."""
    return {tool.name for tool in mcp._tool_manager.list_tools()}


def build_server() -> FastMCP:
    """Build the FastMCP server with exactly the allowlisted tools (guarded)."""
    mcp = FastMCP("siftmesh")
    for name, adapter in tool_adapters().items():
        assert_tool_allowed(name)  # forbidden / off-allowlist can never register
        mcp.add_tool(adapter, name=name)
    registered = registered_tool_names(mcp)
    if registered != set(ALLOWED_TOOLS):
        raise AssertionError(f"registered tools {registered} != allowlist {set(ALLOWED_TOOLS)}")
    return mcp


def run_server() -> None:
    """Launch the gateway over stdio (``siftmesh mcp-serve``)."""
    build_server().run(transport="stdio")
