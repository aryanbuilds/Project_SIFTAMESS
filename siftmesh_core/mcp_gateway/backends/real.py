"""Real in-process forensic backend (D3).

100% in-process Python library calls — zero subprocess, zero shell (criterion 4):
EVTX via ``evtx`` (pyevtx-rs), registry via ``regipy``, prefetch via ``pyscca``
(libscca), MFT via ``mft`` (pymft-rs). Each parser lazy-imports its library and
raises :class:`BackendUnavailableError` if absent (fail closed; ``uv sync --extra
sift``) — never a fake fallback. Output is normalized dict rows; the typed tool
layer wraps them in ``ToolResult`` subclasses with provenance.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from siftmesh_core.mcp_gateway.backends import BackendUnavailableError

# Windows registry autostart locations (HKLM SOFTWARE hive + HKCU NTUSER.DAT hive).
_RUN_KEY_PATHS: tuple[str, ...] = (
    r"\Microsoft\Windows\CurrentVersion\Run",
    r"\Microsoft\Windows\CurrentVersion\RunOnce",
    r"\Software\Microsoft\Windows\CurrentVersion\Run",
    r"\Software\Microsoft\Windows\CurrentVersion\RunOnce",
)


def _system_field(data: dict[str, Any], key: str) -> Any:
    """Pull a field from Event.System, unwrapping ``#text`` attribute objects."""
    value = data.get("Event", {}).get("System", {}).get(key)
    if isinstance(value, dict):
        return value.get("#text", value.get("#attributes"))
    return value


class RealBackend:
    """In-process real forensic backend (default; the demo path)."""

    name = "real"

    def parse_evtx(
        self, path: Path, *, event_id_filter: frozenset[int] | None = None
    ) -> list[dict[str, Any]]:
        try:
            from evtx import PyEvtxParser
        except ImportError as exc:  # pragma: no cover - exercised via fail-closed test
            raise BackendUnavailableError("EVTX backend missing: uv sync --extra sift") from exc

        rows: list[dict[str, Any]] = []
        parser = PyEvtxParser(str(path))
        for record in parser.records_json():
            if record is None:
                continue
            data = json.loads(record["data"])
            event_id_raw = _system_field(data, "EventID")
            try:
                event_id = int(event_id_raw)
            except (TypeError, ValueError):
                event_id = None
            if event_id_filter is not None and event_id not in event_id_filter:
                continue
            time_created = data.get("Event", {}).get("System", {}).get("TimeCreated", {})
            timestamp = record.get("timestamp")
            if not timestamp and isinstance(time_created, dict):
                timestamp = time_created.get("#attributes", {}).get("SystemTime")
            rows.append(
                {
                    "event_record_id": record.get("event_record_id"),
                    "event_id": event_id,
                    "channel": _system_field(data, "Channel"),
                    "computer": _system_field(data, "Computer"),
                    "timestamp_utc": timestamp,
                    "provider": data.get("Event", {})
                    .get("System", {})
                    .get("Provider", {})
                    .get("#attributes", {})
                    .get("Name"),
                    "event_data": data.get("Event", {}).get("EventData"),
                }
            )
        return rows

    def extract_run_keys(self, path: Path) -> list[dict[str, Any]]:
        try:
            from regipy.exceptions import RegistryKeyNotFoundException
            from regipy.registry import RegistryHive
        except ImportError as exc:  # pragma: no cover
            raise BackendUnavailableError("regipy backend missing") from exc

        hive = RegistryHive(str(path))
        rows: list[dict[str, Any]] = []
        for key_path in _RUN_KEY_PATHS:
            try:
                key = hive.get_key(key_path)
            except RegistryKeyNotFoundException:
                continue
            for value in key.get_values():
                # regipy Value records expose name/value/value_type.
                rows.append(
                    {
                        "key_path": key_path,
                        "name": getattr(value, "name", None),
                        "value": getattr(value, "value", None),
                        "value_type": getattr(value, "value_type", None),
                    }
                )
        return rows

    def analyze_prefetch(self, path: Path) -> dict[str, Any]:
        try:
            import pyscca
        except ImportError as exc:  # pragma: no cover
            raise BackendUnavailableError("prefetch backend missing: uv sync --extra sift") from exc

        scca = pyscca.open(str(path))
        last_run_times: list[str] = []
        for index in range(8):  # Win8+ stores up to 8; older formats fewer.
            try:
                value = scca.get_last_run_time(index)
            except (OSError, ValueError, RuntimeError):
                break
            if value is None:
                break
            last_run_times.append(value.isoformat() if hasattr(value, "isoformat") else str(value))
        volumes: list[dict[str, Any]] = []
        for index in range(scca.number_of_volumes):
            vol = scca.get_volume_information(index)
            volumes.append(
                {
                    "device_path": getattr(vol, "device_path", None),
                    "serial_number": getattr(vol, "serial_number", None),
                }
            )
        return {
            "executable_filename": scca.get_executable_filename(),
            "run_count": scca.get_run_count(),
            "prefetch_hash": scca.get_prefetch_hash(),
            "last_run_times": last_run_times,
            "volumes": volumes,
            "filenames": list(scca.filenames),
        }

    def parse_mft(self, path: Path) -> list[dict[str, Any]]:
        try:
            from mft import PyMftParser
        except ImportError as exc:  # pragma: no cover
            raise BackendUnavailableError("MFT backend missing: uv sync --extra sift") from exc

        rows: list[dict[str, Any]] = []
        parser = PyMftParser(str(path))
        for entry in parser.entries_json():
            # entries_json() yields JSON strings, or inline RuntimeError on a bad
            # entry (pymft-rs caveat): type-check and skip, never raise.
            if isinstance(entry, RuntimeError):
                continue
            record = json.loads(entry)
            header = record.get("header", {})
            std_info: dict[str, Any] = {}
            file_name: dict[str, Any] = {}
            for attr in record.get("attributes", []):
                type_code = attr.get("header", {}).get("type_code")
                data = attr.get("data")
                if not isinstance(data, dict):
                    continue
                if type_code == "StandardInformation" and not std_info:
                    std_info = data
                # Prefer the longer (Win32) FileName over the 8.3 short name.
                elif type_code == "FileName" and len(str(data.get("name", ""))) > len(
                    str(file_name.get("name", ""))
                ):
                    file_name = data
            flags = str(header.get("flags", ""))
            rows.append(
                {
                    "record_number": header.get("record_number"),
                    "name": file_name.get("name"),
                    "logical_size": file_name.get("logical_size"),
                    "is_directory": "INDEX" in flags or "DIRECTORY" in flags.upper(),
                    "si_created": std_info.get("created"),
                    "si_modified": std_info.get("modified"),
                    "si_accessed": std_info.get("accessed"),
                }
            )
        return rows
