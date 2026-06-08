"""Deterministic artifact -> family -> tool router (Epic E core).

The single source of truth shared by the Deep Context Agent (E2), the tool map
(E5), and the ``windows_initial_triage`` template (E6/E7). Routing is a pure
function of an artifact's *name and suffix only* — it never opens the file — so a
hostile filename can never trigger a read. Every tool this module names is checked
against the gateway allowlist at import time, so the tool map can never reference a
forbidden or unknown tool.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from siftmesh_core.evidence.manifest import REGISTRY_HIVE_NAMES
from siftmesh_core.mcp_gateway.registry import assert_tool_allowed
from siftmesh_core.schemas.evidence import EvidenceFile, EvidenceManifest

# Fine-grained families — finer than guess_evidence_type (which can't tell a
# Security event log from a PowerShell one, or recognise $MFT).
FineFamily = Literal[
    "evtx_security",
    "evtx_powershell",
    "evtx_other",
    "prefetch",
    "registry_hive",
    "mft",
    "disk_image",
    "memory_image",
    "archive",
    "other",
]

# Fixed render order so context_pack.md / tool_map.md are byte-stable per manifest.
FAMILY_ORDER: tuple[FineFamily, ...] = (
    "evtx_security",
    "evtx_powershell",
    "evtx_other",
    "prefetch",
    "registry_hive",
    "mft",
    "disk_image",
    "memory_image",
    "archive",
    "other",
)

# The single executor tool each family maps to (None = context-only / not actionable).
FAMILY_TOOL_MAP: dict[FineFamily, str | None] = {
    "evtx_security": "parse_evtx_security",
    "evtx_powershell": "parse_evtx_powershell",
    "evtx_other": None,
    "prefetch": "analyze_prefetch",
    "registry_hive": "extract_registry_run_keys",
    "mft": None,
    "disk_image": "extract_artifacts_from_image",
    "memory_image": "analyze_memory",
    "archive": None,
    "other": None,
}

# build_timeline kind for families it can ingest (None = not timeline-capable).
_FAMILY_TIMELINE_KIND: dict[FineFamily, str | None] = {
    "evtx_security": "evtx",
    "evtx_powershell": "evtx",
    "evtx_other": "evtx",
    "prefetch": "prefetch",
    "mft": "mft",
}

# Human-readable family label (deterministic; used in context_pack.md + tool_map.md).
FAMILY_LABEL: dict[FineFamily, str] = {
    "evtx_security": "Windows Security event log",
    "evtx_powershell": "PowerShell Operational log",
    "evtx_other": "Other Windows event log",
    "prefetch": "Prefetch (program execution)",
    "registry_hive": "Windows registry hive",
    "mft": "$MFT filesystem metadata",
    "disk_image": "Disk image",
    "memory_image": "Memory image",
    "archive": "Archive",
    "other": "Unrecognised artifact",
}

# Template-fixed objective per family (deterministic; never echoes evidence text).
# Every family has an entry so context_pack guidance and task objectives stay in sync.
_FAMILY_OBJECTIVE: dict[FineFamily, str] = {
    "evtx_security": "Parse the Windows Security event log for logon, privilege, "
    "and account-management activity.",
    "evtx_powershell": "Parse PowerShell Operational logs (4103/4104) for script-block "
    "and module-logging activity.",
    "evtx_other": "Other Windows event log — folded into the unified timeline; "
    "no dedicated parser task.",
    "prefetch": "Analyse the prefetch artifact for program-execution evidence "
    "(run count, last-run times).",
    "registry_hive": "Extract autostart Run/RunOnce keys from the registry hive.",
    "mft": "$MFT filesystem metadata — feeds the unified timeline (kind=mft); no standalone tool.",
    "disk_image": "Recover loose triage artifacts (event logs, hives, prefetch, $MFT) "
    "from the disk image.",
    "memory_image": "Triage the memory image for processes, network connections, "
    "command lines, and injected code.",
    "archive": "Archive — expand and re-ingest; no in-place triage tool.",
    "other": "Unrecognised artifact type — no automated triage tool.",
}

# Disk-image / memory-image suffixes (lowercased).
_DISK_IMAGE_SUFFIXES = frozenset({".e01", ".raw", ".dd", ".img", ".vmdk"})
_MEMORY_IMAGE_SUFFIXES = frozenset({".mem", ".vmem", ".lime", ".dmp"})
_ARCHIVE_SUFFIXES = frozenset({".zip", ".gz", ".7z", ".tar"})


@dataclass(frozen=True)
class RoutedArtifact:
    """One manifest entry, classified to a fine family + its executor tool."""

    path: str
    sha256: str
    family: FineFamily
    tool: str | None
    timeline_kind: str | None
    objective: str
    actionable: bool


def _classify(name: str, suffix: str) -> FineFamily:
    """Map a (lowercased basename, lowercased suffix) to a fine family.

    Order matters: ``.evtx`` is checked before the registry-name set so an event
    log named ``Security.evtx`` is never mistaken for the bare ``security`` hive,
    and ``powershell`` is matched before the generic evtx fallback.
    """
    if suffix == ".evtx":
        if name == "security.evtx":
            return "evtx_security"
        if "powershell" in name:
            return "evtx_powershell"
        return "evtx_other"
    if suffix == ".pf":
        return "prefetch"
    if name in ("$mft", "mft"):
        return "mft"
    if name in REGISTRY_HIVE_NAMES or suffix in (".dat", ".hve"):
        return "registry_hive"
    if suffix in _DISK_IMAGE_SUFFIXES:
        return "disk_image"
    if suffix in _MEMORY_IMAGE_SUFFIXES:
        return "memory_image"
    if suffix in _ARCHIVE_SUFFIXES:
        return "archive"
    return "other"


def route_artifact(ef: EvidenceFile) -> RoutedArtifact:
    """Classify one evidence file (metadata only — never opens it)."""
    p = Path(ef.path)
    family = _classify(p.name.lower(), p.suffix.lower())
    tool = FAMILY_TOOL_MAP[family]
    return RoutedArtifact(
        path=ef.path,
        sha256=ef.sha256,
        family=family,
        tool=tool,
        timeline_kind=_FAMILY_TIMELINE_KIND.get(family),
        objective=_FAMILY_OBJECTIVE[family],
        actionable=tool is not None,
    )


def route_manifest(manifest: EvidenceManifest) -> list[RoutedArtifact]:
    """Route every manifest entry, preserving manifest order (determinism)."""
    return [route_artifact(ef) for ef in manifest.files]


def _guard_family_tools() -> None:
    """Fail import if any mapped tool is forbidden/unknown (E5 can't drift)."""
    for tool in FAMILY_TOOL_MAP.values():
        if tool is not None:
            assert_tool_allowed(tool)


_guard_family_tools()
