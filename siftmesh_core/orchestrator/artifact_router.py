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
    "browser_history",
    "lnk_jumplist",
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
    "browser_history",
    "lnk_jumplist",
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
    "mft": "parse_mft_filesystem",
    "browser_history": "parse_browser_history",
    "lnk_jumplist": "parse_lnk_jumplists",
    "disk_image": "extract_artifacts_from_image",
    "memory_image": "analyze_memory",
    "archive": None,
    "other": None,
}

# Extra typed tools a specific registry hive feeds BEYOND its primary FAMILY_TOOL_MAP tool
# (multi-tool-per-hive): NTUSER.DAT also yields RecentDocs + MountPoints2; SYSTEM also has USBSTOR.
# Keyed by lowercased hive basename. The planner mints one extra task per (extra tool) over the
# matching hives; the router family stays single-tool (one source of truth per family).
_EXTRA_HIVE_TOOLS: dict[str, tuple[str, ...]] = {
    "ntuser.dat": ("parse_recentdocs_mru", "parse_usb_registry"),
    "system": ("parse_usb_registry",),
}


def extra_tools_for(path: str) -> tuple[str, ...]:
    """Extra typed tools this hive feeds beyond its primary tool (by hive basename), or ()."""
    return _EXTRA_HIVE_TOOLS.get(Path(path).name.lower(), ())


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
    "browser_history": "Browser history database",
    "lnk_jumplist": "LNK shortcut / JumpList",
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
    "mft": "Parse the $MFT for a filesystem inventory (filenames, sizes, timestamps); "
    "also feeds the unified timeline (kind=mft).",
    "browser_history": "Parse the browser history database for visited URLs and downloads "
    "(cloud-storage / webmail destinations).",
    "lnk_jumplist": "Parse the LNK shortcut / JumpList for opened-file target paths "
    "(what the user accessed and where it lived).",
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
    # Browser history DBs: Chromium ``History`` is extension-less; checked before the registry
    # branch so a bare name can never be mistaken for a hive.
    if name in ("history", "places.sqlite"):
        return "browser_history"
    if suffix in (".lnk", ".automaticdestinations-ms", ".customdestinations-ms"):
        return "lnk_jumplist"
    if name in REGISTRY_HIVE_NAMES or suffix in (".dat", ".hve"):
        return "registry_hive"
    if suffix in _DISK_IMAGE_SUFFIXES:
        return "disk_image"
    if suffix in _MEMORY_IMAGE_SUFFIXES:
        return "memory_image"
    if suffix in _ARCHIVE_SUFFIXES:
        return "archive"
    return "other"


def route_path(path: str, sha256: str, *, force_family: FineFamily | None = None) -> RoutedArtifact:
    """Classify a ``(path, sha256)`` pair (metadata only — never opens it).

    ``force_family`` overrides classification — used for derived artifacts whose extension is
    ambiguous (e.g. a decompressed ``.raw`` memory image, which by suffix would look like a disk
    image; hth.2 forces ``memory_image``).
    """
    p = Path(path)
    family = force_family or _classify(p.name.lower(), p.suffix.lower())
    tool = FAMILY_TOOL_MAP[family]
    return RoutedArtifact(
        path=path,
        sha256=sha256,
        family=family,
        tool=tool,
        timeline_kind=_FAMILY_TIMELINE_KIND.get(family),
        objective=_FAMILY_OBJECTIVE[family],
        actionable=tool is not None,
    )


def route_artifact(ef: EvidenceFile) -> RoutedArtifact:
    """Classify one evidence file (metadata only — never opens it)."""
    return route_path(ef.path, ef.sha256)


def route_manifest(manifest: EvidenceManifest) -> list[RoutedArtifact]:
    """Route every manifest entry, preserving manifest order (determinism)."""
    return [route_artifact(ef) for ef in manifest.files]


def timeline_kind_for(path: str) -> str | None:
    """Return the build_timeline ``kind`` for an artifact path, or None if not timeline-capable.

    Used by the executor (Epic F) to reconstruct ``build_timeline``'s ``inputs`` from a
    timeline task's ``input_artifacts`` without importing private router internals.
    """
    p = Path(path)
    return _FAMILY_TIMELINE_KIND.get(_classify(p.name.lower(), p.suffix.lower()))


def _guard_family_tools() -> None:
    """Fail import if any mapped tool is forbidden/unknown (E5 can't drift)."""
    for tool in FAMILY_TOOL_MAP.values():
        if tool is not None:
            assert_tool_allowed(tool)
    for extra in _EXTRA_HIVE_TOOLS.values():
        for tool in extra:
            assert_tool_allowed(tool)


_guard_family_tools()
