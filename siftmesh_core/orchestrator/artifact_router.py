from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from siftmesh_core.evidence.manifest import REGISTRY_HIVE_NAMES
from siftmesh_core.mcp_gateway.registry import assert_tool_allowed
from siftmesh_core.schemas.evidence import EvidenceFile, EvidenceManifest

FineFamily = Literal[
    "evtx_security",
    "evtx_powershell",
    "evtx_other",
    "prefetch",
    "registry_hive",
    "mft",
    "browser_history",
    "lnk_jumplist",
    "shellbag_hive",
    "amcache_hive",
    "usn_journal",
    "disk_image",
    "memory_image",
    "archive",
    "other",
]

FAMILY_ORDER: tuple[FineFamily, ...] = (
    "evtx_security",
    "evtx_powershell",
    "evtx_other",
    "prefetch",
    "registry_hive",
    "mft",
    "browser_history",
    "lnk_jumplist",
    "shellbag_hive",
    "amcache_hive",
    "usn_journal",
    "disk_image",
    "memory_image",
    "archive",
    "other",
)

FAMILY_TOOL_MAP: dict[FineFamily, str | None] = {
    "evtx_security": "parse_evtx_security",
    "evtx_powershell": "parse_evtx_powershell",
    "evtx_other": None,
    "prefetch": "analyze_prefetch",
    "registry_hive": "extract_registry_run_keys",
    "mft": "parse_mft_filesystem",
    "browser_history": "parse_browser_history",
    "lnk_jumplist": "parse_lnk_jumplists",
    "shellbag_hive": "parse_shellbags",
    "amcache_hive": "parse_amcache_shimcache",
    "usn_journal": "parse_usnjrnl",
    "disk_image": "extract_artifacts_from_image",
    "memory_image": "analyze_memory",
    "archive": None,
    "other": None,
}

_EXTRA_HIVE_TOOLS: dict[str, tuple[str, ...]] = {
    "ntuser.dat": ("parse_recentdocs_mru", "parse_usb_registry", "parse_shellbags"),
    "system": ("parse_usb_registry", "parse_amcache_shimcache"),
}


def extra_tools_for(path: str) -> tuple[str, ...]:
    name = Path(path).name.lower()
    for hive, tools in _EXTRA_HIVE_TOOLS.items():
        if name == hive or name.endswith(f"_{hive}"):
            return tools
    return ()


_FAMILY_TIMELINE_KIND: dict[FineFamily, str | None] = {
    "evtx_security": "evtx",
    "evtx_powershell": "evtx",
    "evtx_other": "evtx",
    "prefetch": "prefetch",
    "mft": "mft",
}

FAMILY_LABEL: dict[FineFamily, str] = {
    "evtx_security": "Windows Security event log",
    "evtx_powershell": "PowerShell Operational log",
    "evtx_other": "Other Windows event log",
    "prefetch": "Prefetch (program execution)",
    "registry_hive": "Windows registry hive",
    "mft": "$MFT filesystem metadata",
    "browser_history": "Browser history database",
    "lnk_jumplist": "LNK shortcut / JumpList",
    "shellbag_hive": "Shellbags (UsrClass.dat BagMRU)",
    "amcache_hive": "Amcache (program execution / presence)",
    "usn_journal": "USN change journal ($J)",
    "disk_image": "Disk image",
    "memory_image": "Memory image",
    "archive": "Archive",
    "other": "Unrecognised artifact",
}

_FAMILY_OBJECTIVE: dict[FineFamily, str] = {
    "evtx_security": "Parse the Windows Security event log for logon, privilege, "
    "and account-management activity.",
    "evtx_powershell": "Parse PowerShell Operational logs (4103/4104) for script-block "
    "and module-logging activity.",
    "evtx_other": "Other Windows event log - folded into the unified timeline; "
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
    "shellbag_hive": "Parse shellbags (BagMRU) for browsed-folder history "
    "(including folders no longer on disk).",
    "amcache_hive": "Parse Amcache for program execution / presence "
    "(full path, SHA-1, first-run time).",
    "usn_journal": "Parse the USN change journal for file create/delete/rename activity "
    "(including deleted files), with timestamps.",
    "disk_image": "Recover loose triage artifacts (event logs, hives, prefetch, $MFT) "
    "from the disk image.",
    "memory_image": "Triage the memory image for processes, network connections, "
    "command lines, and injected code.",
    "archive": "Archive - expand and re-ingest; no in-place triage tool.",
    "other": "Unrecognised artifact type - no automated triage tool.",
}

_DISK_IMAGE_SUFFIXES = frozenset({".e01", ".raw", ".dd", ".img", ".vmdk"})
_MEMORY_IMAGE_SUFFIXES = frozenset({".mem", ".vmem", ".lime", ".dmp"})
_ARCHIVE_SUFFIXES = frozenset({".zip", ".gz", ".7z", ".tar"})


@dataclass(frozen=True)
class RoutedArtifact:
    path: str
    sha256: str
    family: FineFamily
    tool: str | None
    timeline_kind: str | None
    objective: str
    actionable: bool


def _classify(name: str, suffix: str) -> FineFamily:
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
    if name in ("history", "places.sqlite"):
        return "browser_history"
    if suffix in (".lnk", ".automaticdestinations-ms", ".customdestinations-ms"):
        return "lnk_jumplist"
    # UsrClass.dat is in REGISTRY_HIVE_NAMES (would misroute to run-keys, which it has none of);
    # its forensic value is shellbags, so special-case it before the generic registry branch.
    if name == "usrclass.dat":
        return "shellbag_hive"
    # Amcache.hve would otherwise hit the ``.hve`` branch -> run-keys (it has none); its value is
    # program-execution, so special-case it before the generic registry branch.
    if name == "amcache.hve":
        return "amcache_hive"
    # USN change journal: the $J ADS, extracted as ``UsnJrnl.$J``.
    if "usnjrnl" in name or suffix == ".$j":
        return "usn_journal"
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
    return route_path(ef.path, ef.sha256)


def route_manifest(manifest: EvidenceManifest) -> list[RoutedArtifact]:
    return [route_artifact(ef) for ef in manifest.files]


def timeline_kind_for(path: str) -> str | None:
    p = Path(path)
    return _FAMILY_TIMELINE_KIND.get(_classify(p.name.lower(), p.suffix.lower()))


def _guard_family_tools() -> None:
    for tool in FAMILY_TOOL_MAP.values():
        if tool is not None:
            assert_tool_allowed(tool)
    for extra in _EXTRA_HIVE_TOOLS.values():
        for tool in extra:
            assert_tool_allowed(tool)


_guard_family_tools()
