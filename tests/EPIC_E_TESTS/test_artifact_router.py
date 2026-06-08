"""Router unit tests — the DRY family->tool source of truth (Epic E core)."""

from __future__ import annotations

from datetime import UTC, datetime

from siftmesh_core.mcp_gateway.registry import ALLOWED_TOOLS, FORBIDDEN_TOOLS
from siftmesh_core.orchestrator.artifact_router import (
    FAMILY_TOOL_MAP,
    route_artifact,
)
from siftmesh_core.schemas.evidence import EvidenceFile


def _ef(path: str) -> EvidenceFile:
    return EvidenceFile(
        path=path,
        sha256="a" * 64,
        size_bytes=1,
        mtime_utc=datetime(2026, 1, 1, tzinfo=UTC),
        evidence_type="x",
    )


def test_security_evtx_vs_security_hive_disambiguated() -> None:
    assert route_artifact(_ef("Security.evtx")).family == "evtx_security"
    assert route_artifact(_ef("Security.evtx")).tool == "parse_evtx_security"
    # the bare SECURITY registry hive (no extension) must not collide with the event log
    assert route_artifact(_ef("Windows/System32/config/SECURITY")).family == "registry_hive"


def test_powershell_evtx_routes_before_generic_evtx() -> None:
    r = route_artifact(_ef("Microsoft-Windows-PowerShell%4Operational.evtx"))
    assert r.family == "evtx_powershell"
    assert r.tool == "parse_evtx_powershell"


def test_other_evtx_and_mft_are_context_only() -> None:
    sysr = route_artifact(_ef("System.evtx"))
    assert sysr.family == "evtx_other"
    assert sysr.tool is None and sysr.actionable is False
    assert sysr.timeline_kind == "evtx"  # still feeds the timeline
    mft = route_artifact(_ef("$MFT"))
    assert mft.family == "mft" and mft.tool is None and mft.actionable is False
    assert mft.timeline_kind == "mft"


def test_prefetch_registry_image_memory_route() -> None:
    assert route_artifact(_ef("CMD.EXE-1.pf")).tool == "analyze_prefetch"
    assert route_artifact(_ef("Users/alice/NTUSER.DAT")).tool == "extract_registry_run_keys"
    assert route_artifact(_ef("disk.E01")).tool == "extract_artifacts_from_image"
    assert route_artifact(_ef("memory.vmem")).tool == "analyze_memory"


def test_archive_and_unknown_are_not_actionable() -> None:
    assert route_artifact(_ef("bundle.zip")).actionable is False
    assert route_artifact(_ef("notes.bin")).family == "other"


def test_family_tool_map_is_entirely_allowlisted() -> None:
    tools = {t for t in FAMILY_TOOL_MAP.values() if t}
    assert tools <= set(ALLOWED_TOOLS)
    assert not (tools & FORBIDDEN_TOOLS)
