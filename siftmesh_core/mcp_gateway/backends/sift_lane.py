"""SIFT-lane backend (D12) — drive Protocol SIFT's real EZ Tools behind the typed interface.

Mirrors :class:`RealBackend` so SIFT-host execution is a **config flip** (``backend_mode``),
not a fork. Each method shells out to an Eric-Zimmerman tool via **fixed-argv**
``subprocess.run(shell=False)`` — ``dotnet <Tool>.dll`` (EZ Tools are .NET) — parses the tool's
JSON output, and normalizes to the **exact same row dicts** :class:`RealBackend` returns, so the
typed tools and their results are unchanged.

REAL-ONLY / fail-closed (CLAUDE.md §2B/§6): a missing ``dotnet`` or tool DLL raises
:class:`BackendUnavailableError` (never a fake result); a non-zero tool exit raises (the tool layer
records ``status=error``). Only the validated evidence path + a scratch temp dir are passed as argv
elements — no evidence string is ever interpolated into a shell. ``analyze_prefetch`` fails closed:
PECmd is not part of the EZ Tools install on the SANS SIFT host.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from siftmesh_core.config import load_settings
from siftmesh_core.mcp_gateway.backends import BackendUnavailableError

_EVTX_TIMEOUT = 600
_MFT_TIMEOUT = 1800  # a full $MFT can be hundreds of MB
_RECMD_TIMEOUT = 600

# EZ tool DLL location relative to the EZ Tools install dir.
_DLL_PARTS: dict[str, tuple[str, ...]] = {
    "evtx": ("EvtxeCmd", "EvtxECmd.dll"),
    "mft": ("MFTECmd.dll",),
    "recmd": ("RECmd", "RECmd.dll"),
}

# RECmd batch (.reb) targeting autostart Run/RunOnce across HKLM SOFTWARE + HKCU NTUSER,
# mirroring RealBackend._RUN_KEY_PATHS. RECmd applies entries whose HiveType matches the hive.
_RUNKEYS_BATCH = """Description: SIFTMesh autostart Run/RunOnce keys
Author: SIFTMesh
Version: 1.0
Id: 7f3b1c2a-0000-4000-8000-000000000001
Keys:
    -
        Description: HKLM Run
        HiveType: Software
        Category: Autostart
        KeyPath: Microsoft\\Windows\\CurrentVersion\\Run
        Recursive: false
        Comment: ""
    -
        Description: HKLM RunOnce
        HiveType: Software
        Category: Autostart
        KeyPath: Microsoft\\Windows\\CurrentVersion\\RunOnce
        Recursive: false
        Comment: ""
    -
        Description: HKCU Run
        HiveType: NtUser
        Category: Autostart
        KeyPath: Software\\Microsoft\\Windows\\CurrentVersion\\Run
        Recursive: false
        Comment: ""
    -
        Description: HKCU RunOnce
        HiveType: NtUser
        Category: Autostart
        KeyPath: Software\\Microsoft\\Windows\\CurrentVersion\\RunOnce
        Recursive: false
        Comment: ""
"""


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Read an EZ tool JSONL output file (utf-8-sig strips the BOM EvtxECmd writes)."""
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


class SiftLaneBackend:
    """SIFT-host backend driving EZ Tools via fixed-argv ``dotnet`` subprocess (D12)."""

    name = "sift_lane"

    def __init__(self, ez_tools_dir: str | Path | None = None) -> None:
        self.ez_tools_dir = Path(ez_tools_dir or load_settings().ez_tools_dir)

    # ── tool resolution (fail closed) ──────────────────────────────────────
    def _dotnet(self) -> str:
        found = shutil.which("dotnet")
        if found is None:
            raise BackendUnavailableError(
                "dotnet not found on PATH (EZ Tools runtime); fails closed"
            )
        return found

    def _dll(self, key: str) -> Path:
        dll = self.ez_tools_dir.joinpath(*_DLL_PARTS[key])
        if not dll.is_file():
            raise BackendUnavailableError(
                f"EZ Tool {key!r} not found at {dll} (install EZ Tools / set ez_tools_dir)"
            )
        return dll

    def _run(self, argv: list[str], *, timeout: int) -> None:
        proc = subprocess.run(  # fixed argv, shell=False, validated evidence path
            argv, capture_output=True, text=True, timeout=timeout, check=False
        )
        if proc.returncode != 0:
            raise RuntimeError(
                f"{Path(argv[1]).name} failed: {proc.stderr.strip() or 'non-zero exit'}"
            )

    # ── typed primitives (normalized to RealBackend row shapes) ─────────────
    def parse_evtx(
        self,
        path: Path,
        *,
        event_id_filter: frozenset[int] | None = None,
        channel_filter: frozenset[str] | None = None,
    ) -> list[dict[str, Any]]:
        dll = self._dll("evtx")
        with tempfile.TemporaryDirectory(prefix="siftmesh-evtx-") as tmp:
            out = Path(tmp) / "evtx.json"
            self._run(
                [self._dotnet(), str(dll), "-f", str(path), "--json", tmp, "--jsonf", out.name],
                timeout=_EVTX_TIMEOUT,
            )
            rows: list[dict[str, Any]] = []
            for r in _read_jsonl(out):
                raw_event_id = r.get("EventId")
                try:
                    event_id = int(raw_event_id) if raw_event_id is not None else None
                except (TypeError, ValueError):
                    event_id = None
                if event_id_filter is not None and event_id not in event_id_filter:
                    continue
                channel = r.get("Channel")
                if channel_filter is not None and channel not in channel_filter:
                    continue
                raw_record_id = r.get("EventRecordId")
                try:
                    record_id = int(raw_record_id) if raw_record_id is not None else None
                except (TypeError, ValueError):
                    record_id = None
                event_data: Any = None
                payload = r.get("Payload")
                if isinstance(payload, str) and payload:
                    try:
                        event_data = json.loads(payload).get("EventData")
                    except (json.JSONDecodeError, AttributeError):
                        event_data = None
                rows.append(
                    {
                        "event_record_id": record_id,
                        "event_id": event_id,
                        "channel": channel,
                        "computer": r.get("Computer"),
                        "timestamp_utc": r.get("TimeCreated"),
                        "provider": r.get("Provider"),
                        "event_data": event_data,
                    }
                )
            return rows

    def analyze_prefetch(self, path: Path) -> dict[str, Any]:
        raise BackendUnavailableError(
            "PECmd is not installed in the EZ Tools set on this SIFT host; "
            "use backend_mode='real' (pyscca) for prefetch. Fails closed."
        )

    def extract_run_keys(self, path: Path) -> list[dict[str, Any]]:
        dll = self._dll("recmd")
        with tempfile.TemporaryDirectory(prefix="siftmesh-recmd-") as tmp:
            batch = Path(tmp) / "runkeys.reb"
            batch.write_text(_RUNKEYS_BATCH, encoding="utf-8")
            out = Path(tmp) / "recmd.json"
            self._run(
                [
                    self._dotnet(),
                    str(dll),
                    "-f",
                    str(path),
                    "--bn",
                    str(batch),
                    "--nl",
                    "true",
                    "--json",
                    tmp,
                    "--jsonf",
                    out.name,
                ],
                timeout=_RECMD_TIMEOUT,
            )
            rows: list[dict[str, Any]] = []
            for r in _read_jsonl(out):
                key_path = str(r.get("KeyPath", "")).removeprefix("ROOT\\")
                rows.append(
                    {
                        "key_path": key_path,
                        "name": r.get("ValueName"),
                        "value": r.get("ValueData"),
                        "value_type": r.get("ValueType"),
                    }
                )
            return rows

    def extract_recentdocs(self, path: Path) -> list[dict[str, Any]]:
        raise BackendUnavailableError(
            "RecentDocs via sift_lane is not wired (no RECmd batch shipped); "
            "use backend_mode='real' (regipy). Fails closed."
        )

    def extract_usb_devices(self, path: Path) -> list[dict[str, Any]]:
        raise BackendUnavailableError(
            "USB registry parsing via sift_lane is not wired (no RECmd batch shipped); "
            "use backend_mode='real' (regipy). Fails closed."
        )

    def parse_browser_history(self, path: Path) -> list[dict[str, Any]]:
        raise BackendUnavailableError(
            "browser-history parsing via sift_lane is not wired (no EZ browser tool); "
            "use backend_mode='real' (stdlib sqlite3). Fails closed."
        )

    def parse_lnk_jumplists(self, path: Path) -> list[dict[str, Any]]:
        raise BackendUnavailableError(
            "LNK/JumpList parsing via sift_lane (JLECmd/LECmd) is not wired; "
            "use backend_mode='real' (LnkParse3 + olefile). Fails closed."
        )

    def parse_mft(self, path: Path) -> list[dict[str, Any]]:
        dll = self._dll("mft")
        with tempfile.TemporaryDirectory(prefix="siftmesh-mft-") as tmp:
            out = Path(tmp) / "mft.json"
            self._run(
                [self._dotnet(), str(dll), "-f", str(path), "--json", tmp, "--jsonf", out.name],
                timeout=_MFT_TIMEOUT,
            )
            rows: list[dict[str, Any]] = []
            for r in _read_jsonl(out):
                rows.append(
                    {
                        "record_number": r.get("EntryNumber"),
                        "name": r.get("FileName"),
                        "logical_size": r.get("FileSize"),
                        "is_directory": r.get("IsDirectory"),
                        "si_created": r.get("Created0x10"),
                        "si_modified": r.get("LastModified0x10"),
                        "si_accessed": r.get("LastAccess0x10"),
                    }
                )
            return rows
