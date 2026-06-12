"""FastMCP server (D1) — the thin agent-facing adapter over the typed tools.

Registers EXACTLY the allowlisted forensic tools (CLAUDE.md §7) on a FastMCP
stdio server, each guarded by :func:`assert_tool_allowed` at registration so a
forbidden / off-allowlist name can never be exposed (criterion 4). The adapters are
thin: they take primitive args an agent can supply and delegate to the same service
functions the CLI calls directly (CLI-first). Returns are ``ToolResult`` subclasses
(structured MCP output).
"""

from __future__ import annotations

import os
from typing import Any

from mcp.server.fastmcp import FastMCP

from siftmesh_core.mcp_gateway.registry import ALLOWED_TOOLS, assert_tool_allowed
from siftmesh_core.mcp_gateway.tools.amcache_tools import (
    AmcacheShimcacheResult,
    parse_amcache_shimcache,
)
from siftmesh_core.mcp_gateway.tools.browser_tools import (
    BrowserHistoryResult,
    parse_browser_history,
)
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
from siftmesh_core.mcp_gateway.tools.image_tools import (
    ImageExtractionResult,
    extract_artifacts_from_image,
)
from siftmesh_core.mcp_gateway.tools.lnk_tools import LnkJumplistResult, parse_lnk_jumplists
from siftmesh_core.mcp_gateway.tools.memory_tools import MemoryAnalysisResult, analyze_memory
from siftmesh_core.mcp_gateway.tools.mft_tools import MftFilesystemResult, parse_mft_filesystem
from siftmesh_core.mcp_gateway.tools.prefetch_tools import PrefetchResult, analyze_prefetch
from siftmesh_core.mcp_gateway.tools.recentdocs_tools import RecentDocsResult, parse_recentdocs_mru
from siftmesh_core.mcp_gateway.tools.registry_tools import RunKeysResult, extract_registry_run_keys
from siftmesh_core.mcp_gateway.tools.shellbag_tools import ShellbagResult, parse_shellbags
from siftmesh_core.mcp_gateway.tools.super_timeline_tools import (
    SuperTimelineResult,
    build_super_timeline,
)
from siftmesh_core.mcp_gateway.tools.timeline_tools import TimelineResult, build_timeline
from siftmesh_core.mcp_gateway.tools.usb_tools import UsbRegistryResult, parse_usb_registry
from siftmesh_core.mcp_gateway.tools.usn_tools import UsnJournalResult, parse_usnjrnl
from siftmesh_core.mcp_gateway.tools.validation_tools import (
    ClaimValidationResult,
    validate_claim_evidence,
)

# ── Run scoping (K3) ────────────────────────────────────────────────────────
# The agent NEVER chooses the run/evidence roots — the dispatching adapter scopes the server to the
# active run via SIFTMESH_RUN_ROOT / SIFTMESH_EVIDENCE_ROOT (set by claude_adapter's mcp_config).
# The agent-facing tools below therefore take only artifact-specific args, removing the confused-
# deputy surface (a hostile prompt can't redirect a tool at another run/evidence tree). Missing env
# => fail closed: refuse to run an unscoped forensic tool rather than guess a root.

_RUN_ROOT_ENV = "SIFTMESH_RUN_ROOT"
_EVIDENCE_ROOT_ENV = "SIFTMESH_EVIDENCE_ROOT"


def _run_scope() -> tuple[str, str]:
    """The (run_root, evidence_root) the adapter scoped this server to; fail closed if unset."""
    run_root = os.environ.get(_RUN_ROOT_ENV)
    evidence_root = os.environ.get(_EVIDENCE_ROOT_ENV)
    if not run_root or not evidence_root:
        raise RuntimeError(
            f"{_RUN_ROOT_ENV} and {_EVIDENCE_ROOT_ENV} must be set by the dispatching adapter; "
            "refusing to run an unscoped forensic tool."
        )
    return run_root, evidence_root


# ── Thin MCP adapters (artifact-specific args -> service functions; roots from env) ──


def _compute_hash_manifest() -> HashManifestResult:
    run_root, evidence_root = _run_scope()
    return compute_hash_manifest(run_root, evidence_root=evidence_root)


def _create_readonly_evidence_vault() -> ReadonlyVaultResult:
    run_root, evidence_root = _run_scope()
    return create_readonly_evidence_vault(run_root, evidence_root=evidence_root)


def _parse_evtx_security(source_artifact: str) -> EvtxParseResult:
    run_root, evidence_root = _run_scope()
    return parse_evtx_security(
        run_root, source_artifact=source_artifact, evidence_root=evidence_root
    )


def _parse_evtx_powershell(source_artifact: str) -> EvtxParseResult:
    run_root, evidence_root = _run_scope()
    return parse_evtx_powershell(
        run_root, source_artifact=source_artifact, evidence_root=evidence_root
    )


def _analyze_prefetch(source_artifact: str) -> PrefetchResult:
    run_root, evidence_root = _run_scope()
    return analyze_prefetch(run_root, source_artifact=source_artifact, evidence_root=evidence_root)


def _extract_registry_run_keys(source_artifact: str) -> RunKeysResult:
    run_root, evidence_root = _run_scope()
    return extract_registry_run_keys(
        run_root, source_artifact=source_artifact, evidence_root=evidence_root
    )


def _build_timeline(inputs: list[dict[str, str]]) -> TimelineResult:
    run_root, evidence_root = _run_scope()
    return build_timeline(run_root, inputs=inputs, evidence_root=evidence_root)


def _validate_claim_evidence(claim: dict[str, Any]) -> ClaimValidationResult:
    run_root, evidence_root = _run_scope()
    return validate_claim_evidence(run_root, claim, evidence_root=evidence_root)


def _extract_artifacts_from_image(
    image_artifact: str, keys: list[str] | None = None
) -> ImageExtractionResult:
    run_root, evidence_root = _run_scope()
    return extract_artifacts_from_image(
        run_root, image_artifact=image_artifact, evidence_root=evidence_root, keys=keys
    )


def _analyze_memory(memory_artifact: str, plugins: list[str] | None = None) -> MemoryAnalysisResult:
    run_root, evidence_root = _run_scope()
    return analyze_memory(
        run_root, memory_artifact=memory_artifact, evidence_root=evidence_root, plugins=plugins
    )


def _parse_mft_filesystem(source_artifact: str) -> MftFilesystemResult:
    run_root, evidence_root = _run_scope()
    return parse_mft_filesystem(
        run_root, source_artifact=source_artifact, evidence_root=evidence_root
    )


def _parse_recentdocs_mru(source_artifact: str) -> RecentDocsResult:
    run_root, evidence_root = _run_scope()
    return parse_recentdocs_mru(
        run_root, source_artifact=source_artifact, evidence_root=evidence_root
    )


def _parse_usb_registry(source_artifact: str) -> UsbRegistryResult:
    run_root, evidence_root = _run_scope()
    return parse_usb_registry(
        run_root, source_artifact=source_artifact, evidence_root=evidence_root
    )


def _parse_browser_history(source_artifact: str) -> BrowserHistoryResult:
    run_root, evidence_root = _run_scope()
    return parse_browser_history(
        run_root, source_artifact=source_artifact, evidence_root=evidence_root
    )


def _parse_lnk_jumplists(source_artifact: str) -> LnkJumplistResult:
    run_root, evidence_root = _run_scope()
    return parse_lnk_jumplists(
        run_root, source_artifact=source_artifact, evidence_root=evidence_root
    )


def _parse_shellbags(source_artifact: str) -> ShellbagResult:
    run_root, evidence_root = _run_scope()
    return parse_shellbags(run_root, source_artifact=source_artifact, evidence_root=evidence_root)


def _parse_amcache_shimcache(source_artifact: str) -> AmcacheShimcacheResult:
    run_root, evidence_root = _run_scope()
    return parse_amcache_shimcache(
        run_root, source_artifact=source_artifact, evidence_root=evidence_root
    )


def _parse_usnjrnl(source_artifact: str) -> UsnJournalResult:
    run_root, evidence_root = _run_scope()
    return parse_usnjrnl(run_root, source_artifact=source_artifact, evidence_root=evidence_root)


def _build_super_timeline(image_artifact: str) -> SuperTimelineResult:
    run_root, evidence_root = _run_scope()
    return build_super_timeline(
        run_root, image_artifact=image_artifact, evidence_root=evidence_root
    )


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
        "extract_artifacts_from_image": _extract_artifacts_from_image,
        "analyze_memory": _analyze_memory,
        "parse_mft_filesystem": _parse_mft_filesystem,
        "parse_recentdocs_mru": _parse_recentdocs_mru,
        "parse_usb_registry": _parse_usb_registry,
        "parse_browser_history": _parse_browser_history,
        "parse_lnk_jumplists": _parse_lnk_jumplists,
        "parse_shellbags": _parse_shellbags,
        "parse_amcache_shimcache": _parse_amcache_shimcache,
        "parse_usnjrnl": _parse_usnjrnl,
        "build_super_timeline": _build_super_timeline,
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
