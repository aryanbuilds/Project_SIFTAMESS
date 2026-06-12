from __future__ import annotations

import json
import shutil
import sqlite3
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from siftmesh_core.mcp_gateway.backends import BackendUnavailableError

_RUN_KEY_PATHS: tuple[str, ...] = (
    r"\Microsoft\Windows\CurrentVersion\Run",
    r"\Microsoft\Windows\CurrentVersion\RunOnce",
    r"\Software\Microsoft\Windows\CurrentVersion\Run",
    r"\Software\Microsoft\Windows\CurrentVersion\RunOnce",
)

_RECENTDOCS_PATH = r"\Software\Microsoft\Windows\CurrentVersion\Explorer\RecentDocs"
_MOUNTPOINTS2_PATH = r"\Software\Microsoft\Windows\CurrentVersion\Explorer\MountPoints2"


def _filetime_iso(filetime: int | None) -> str | None:
    if not filetime:
        return None
    try:
        dt = datetime(1601, 1, 1, tzinfo=UTC) + timedelta(microseconds=int(filetime) // 10)
    except (ValueError, OverflowError):
        return None
    return dt.isoformat().replace("+00:00", "Z")


def _epoch_us_iso(value: int | None, epoch_year: int) -> str | None:
    if not value:
        return None
    try:
        dt = datetime(epoch_year, 1, 1, tzinfo=UTC) + timedelta(microseconds=int(value))
    except (ValueError, OverflowError):
        return None
    return dt.isoformat().replace("+00:00", "Z")


def _decode_utf16_name(blob: Any) -> str | None:
    if not isinstance(blob, bytes | bytearray):
        return None
    name = bytes(blob).split(b"\x00\x00", 1)[0].decode("utf-16-le", errors="ignore")
    name = name.rstrip("\x00").strip()
    return name or None


_LNK_HEADER = b"\x4c\x00\x00\x00" + bytes.fromhex("0114020000000000c000000000000046")

_USN_REASONS: tuple[tuple[int, str], ...] = (
    (0x00000001, "DATA_OVERWRITE"),
    (0x00000002, "DATA_EXTEND"),
    (0x00000004, "DATA_TRUNCATION"),
    (0x00000100, "FILE_CREATE"),
    (0x00000200, "FILE_DELETE"),
    (0x00000400, "EA_CHANGE"),
    (0x00000800, "SECURITY_CHANGE"),
    (0x00001000, "RENAME_OLD_NAME"),
    (0x00002000, "RENAME_NEW_NAME"),
    (0x00004000, "INDEXABLE_CHANGE"),
    (0x00008000, "BASIC_INFO_CHANGE"),
    (0x00010000, "HARD_LINK_CHANGE"),
    (0x00020000, "COMPRESSION_CHANGE"),
    (0x00040000, "ENCRYPTION_CHANGE"),
    (0x00080000, "OBJECT_ID_CHANGE"),
    (0x00100000, "REPARSE_POINT_CHANGE"),
    (0x00200000, "STREAM_CHANGE"),
    (0x80000000, "CLOSE"),
)


def _decode_usn_reason(mask: int) -> list[str] | None:
    return [name for bit, name in _USN_REASONS if mask & bit] or None


def _dt_iso(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return str(value.isoformat()).replace("+00:00", "Z")
    return str(value).replace("+00:00", "Z")


def _lnk_row(blob: bytes, *, kind: str, source: str) -> dict[str, Any]:
    import LnkParse3

    j = LnkParse3.lnk_file(indata=blob).get_json()
    header = j.get("header", {}) or {}
    info = j.get("link_info", {}) or {}
    data = j.get("data", {}) or {}
    lbp = info.get("local_base_path")
    target = (str(lbp) + str(info.get("common_path_suffix") or "")) if lbp else None
    return {
        "kind": kind,
        "source": source,
        "target_path": target,
        "target_size": header.get("file_size"),
        "working_dir": data.get("working_directory"),
        "relative_path": data.get("relative_path"),
        "arguments": data.get("command_line_arguments"),
        "created_utc": _dt_iso(header.get("creation_time")),
        "accessed_utc": _dt_iso(header.get("accessed_time")),
        "modified_utc": _dt_iso(header.get("modified_time")),
    }


def _auto_dest_rows(path: Path) -> list[dict[str, Any]]:
    try:
        import olefile
    except ImportError as exc:  # pragma: no cover
        raise BackendUnavailableError(
            "JumpList OLE backend missing (olefile); uv sync --all-extras"
        ) from exc

    rows: list[dict[str, Any]] = []
    ole = olefile.OleFileIO(str(path))
    try:
        for entry in ole.listdir():
            leaf = entry[-1]
            if not (isinstance(leaf, str) and leaf.isdigit()):
                continue
            try:
                rows.append(
                    _lnk_row(ole.openstream(entry).read(), kind="jumplist", source="/".join(entry))
                )
            except Exception:
                continue
    finally:
        ole.close()
    return rows


def _custom_dest_rows(path: Path) -> list[dict[str, Any]]:
    blob = path.read_bytes()
    offsets: list[int] = []
    i = blob.find(_LNK_HEADER)
    while i != -1:
        offsets.append(i)
        i = blob.find(_LNK_HEADER, i + 20)
    rows: list[dict[str, Any]] = []
    for k, start in enumerate(offsets):
        end = offsets[k + 1] if k + 1 < len(offsets) else len(blob)
        try:
            rows.append(_lnk_row(blob[start:end], kind="jumplist", source=f"entry-{k}"))
        except Exception:
            continue
    return rows


def _run_regipy_plugin(plugin: Any, fail_msg: str) -> list[dict[str, Any]]:
    try:
        if not plugin.can_run():
            return []
    except Exception:
        return []
    try:
        out = plugin.run()
    except ModuleNotFoundError as exc:  # pragma: no cover - exercised via fail-closed test
        raise BackendUnavailableError(fail_msg) from exc
    return (out if out is not None else getattr(plugin, "entries", [])) or []


def _shellbag_row(entry: dict[str, Any], source_hive: str) -> dict[str, Any]:
    return {
        "source_hive": source_hive,
        "bag_path": entry.get("reg_path"),
        "value_name": entry.get("value_name"),
        "shell_type": entry.get("shell_type"),
        "folder_path": entry.get("path") or entry.get("value"),
        "value": entry.get("value"),
        "last_write_utc": _dt_iso(entry.get("last_write")),
        "created_utc": _dt_iso(entry.get("creation_time")),
        "modified_utc": _dt_iso(entry.get("modification_time")),
        "accessed_utc": _dt_iso(entry.get("access_time")),
        "mru_order": entry.get("mru_order"),
    }


def _system_field(data: dict[str, Any], key: str) -> Any:
    value = data.get("Event", {}).get("System", {}).get(key)
    if isinstance(value, dict):
        return value.get("#text", value.get("#attributes"))
    return value


class RealBackend:
    name = "real"

    def parse_evtx(
        self,
        path: Path,
        *,
        event_id_filter: frozenset[int] | None = None,
        channel_filter: frozenset[str] | None = None,
    ) -> list[dict[str, Any]]:
        try:
            from evtx import PyEvtxParser
        except ImportError as exc:  # pragma: no cover - exercised via fail-closed test
            raise BackendUnavailableError(
                "EVTX backend missing: run `siftmesh doctor --setup`"
            ) from exc

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
            channel = _system_field(data, "Channel")
            if channel_filter is not None and channel not in channel_filter:
                continue
            time_created = data.get("Event", {}).get("System", {}).get("TimeCreated", {})
            timestamp = record.get("timestamp")
            if not timestamp and isinstance(time_created, dict):
                timestamp = time_created.get("#attributes", {}).get("SystemTime")
            rows.append(
                {
                    "event_record_id": record.get("event_record_id"),
                    "event_id": event_id,
                    "channel": channel,
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
            raise BackendUnavailableError(
                "prefetch backend missing: run `siftmesh doctor --setup`"
            ) from exc

        scca = pyscca.open(str(path))
        last_run_times: list[str] = []
        for index in range(8):
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

    def extract_recentdocs(self, path: Path) -> list[dict[str, Any]]:
        try:
            from regipy.exceptions import RegistryKeyNotFoundException
            from regipy.registry import RegistryHive
        except ImportError as exc:  # pragma: no cover
            raise BackendUnavailableError("regipy backend missing") from exc

        hive = RegistryHive(str(path))
        try:
            root = hive.get_key(_RECENTDOCS_PATH)
        except RegistryKeyNotFoundException:
            return []
        keys = [("RecentDocs", root)]
        keys.extend((sub.name, sub) for sub in root.iter_subkeys())
        rows: list[dict[str, Any]] = []
        for key_name, key in keys:
            last_write = _filetime_iso(getattr(getattr(key, "header", None), "last_modified", None))
            for value in key.get_values():
                if getattr(value, "name", None) == "MRUListEx":
                    continue
                name = _decode_utf16_name(getattr(value, "value", None))
                if name:
                    rows.append(
                        {
                            "source_key": key_name,
                            "value_name": getattr(value, "name", None),
                            "name": name,
                            "last_write_utc": last_write,
                        }
                    )
        return rows

    def extract_usb_devices(self, path: Path) -> list[dict[str, Any]]:
        try:
            from regipy.exceptions import RegistryKeyNotFoundException
            from regipy.registry import RegistryHive
        except ImportError as exc:  # pragma: no cover
            raise BackendUnavailableError("regipy backend missing") from exc

        hive = RegistryHive(str(path))
        rows: list[dict[str, Any]] = []

        try:
            mp = hive.get_key(_MOUNTPOINTS2_PATH)
        except RegistryKeyNotFoundException:
            mp = None
        if mp is not None:
            for sub in mp.iter_subkeys():
                rows.append(
                    {
                        "source_key": "MountPoints2",
                        "device": sub.name,
                        "last_write_utc": _filetime_iso(
                            getattr(getattr(sub, "header", None), "last_modified", None)
                        ),
                    }
                )

        control_set = "ControlSet001"
        try:
            select = hive.get_key(r"\Select")
            current = next(
                (v.value for v in select.get_values() if getattr(v, "name", None) == "Current"),
                None,
            )
            if current is not None:
                control_set = f"ControlSet{int(current):03d}"
        except RegistryKeyNotFoundException:
            pass
        try:
            usbstor = hive.get_key(rf"\{control_set}\Enum\USBSTOR")
        except RegistryKeyNotFoundException:
            usbstor = None
        if usbstor is not None:
            for device_class in usbstor.iter_subkeys():
                for instance in device_class.iter_subkeys():
                    values = {
                        getattr(v, "name", None): getattr(v, "value", None)
                        for v in instance.get_values()
                    }
                    rows.append(
                        {
                            "source_key": f"USBSTOR\\{device_class.name}",
                            "device": instance.name,
                            "friendly_name": values.get("FriendlyName"),
                            "last_write_utc": _filetime_iso(
                                getattr(getattr(instance, "header", None), "last_modified", None)
                            ),
                        }
                    )
        return rows

    def parse_browser_history(self, path: Path) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        with tempfile.TemporaryDirectory(prefix="siftmesh-browser-") as tmp:
            copy = Path(tmp) / "history.db"
            shutil.copyfile(path, copy)
            conn = sqlite3.connect(f"file:{copy}?mode=ro&immutable=1", uri=True)
            try:
                conn.row_factory = sqlite3.Row
                tables = {
                    r[0]
                    for r in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()
                }
                if "urls" in tables:
                    rows.extend(self._chromium_history(conn, tables))
                elif "moz_places" in tables:
                    rows.extend(self._firefox_history(conn, tables))
                else:
                    raise ValueError("unrecognised browser history schema (no urls/moz_places)")
            finally:
                conn.close()
        return rows

    @staticmethod
    def _chromium_history(conn: sqlite3.Connection, tables: set[str]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for r in conn.execute(
            "SELECT url, title, visit_count, last_visit_time FROM urls "
            "ORDER BY last_visit_time DESC, url"
        ):
            rows.append(
                {
                    "kind": "visit",
                    "url": r["url"],
                    "title": r["title"],
                    "visit_count": r["visit_count"],
                    "last_visit_utc": _epoch_us_iso(r["last_visit_time"], 1601),
                    "target_path": None,
                    "source": "chromium",
                }
            )
        if "downloads" in tables:
            try:
                cur = conn.execute(
                    "SELECT tab_url, target_path, total_bytes, start_time FROM downloads "
                    "ORDER BY target_path"
                )
                for r in cur:
                    rows.append(
                        {
                            "kind": "download",
                            "url": r["tab_url"],
                            "title": None,
                            "visit_count": None,
                            "last_visit_utc": _epoch_us_iso(r["start_time"], 1601),
                            "target_path": r["target_path"],
                            "total_bytes": r["total_bytes"],
                            "source": "chromium",
                        }
                    )
            except sqlite3.OperationalError:
                pass
        return rows

    @staticmethod
    def _firefox_history(conn: sqlite3.Connection, tables: set[str]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for r in conn.execute(
            "SELECT url, title, visit_count, last_visit_date FROM moz_places "
            "WHERE last_visit_date IS NOT NULL ORDER BY last_visit_date DESC, url"
        ):
            rows.append(
                {
                    "kind": "visit",
                    "url": r["url"],
                    "title": r["title"],
                    "visit_count": r["visit_count"],
                    "last_visit_utc": _epoch_us_iso(r["last_visit_date"], 1970),
                    "target_path": None,
                    "source": "firefox",
                }
            )
        if {"moz_annos", "moz_anno_attributes"} <= tables:
            try:
                cur = conn.execute(
                    "SELECT p.url AS url, a.content AS dest FROM moz_annos a "
                    "JOIN moz_places p ON a.place_id = p.id "
                    "JOIN moz_anno_attributes n ON a.anno_attribute_id = n.id "
                    "WHERE n.name = 'downloads/destinationFileURI' ORDER BY p.url"
                )
                for r in cur:
                    rows.append(
                        {
                            "kind": "download",
                            "url": r["url"],
                            "title": None,
                            "visit_count": None,
                            "last_visit_utc": None,
                            "target_path": r["dest"],
                            "source": "firefox",
                        }
                    )
            except sqlite3.OperationalError:
                pass
        return rows

    def parse_lnk_jumplists(self, path: Path) -> list[dict[str, Any]]:
        try:
            import LnkParse3  # noqa: F401
        except ImportError as exc:  # pragma: no cover
            raise BackendUnavailableError(
                "LNK backend missing (LnkParse3); uv sync --all-extras"
            ) from exc

        suffix = path.suffix.lower()
        if suffix == ".automaticdestinations-ms":
            return _auto_dest_rows(path)
        if suffix == ".customdestinations-ms":
            return _custom_dest_rows(path)
        return [_lnk_row(path.read_bytes(), kind="lnk", source=path.name)]

    def extract_shellbags(self, path: Path) -> list[dict[str, Any]]:
        try:
            from regipy.plugins.ntuser.shellbags_ntuser import ShellBagNtuserPlugin
            from regipy.plugins.usrclass.shellbags_usrclass import ShellBagUsrclassPlugin
            from regipy.registry import RegistryHive
        except ImportError as exc:  # pragma: no cover
            raise BackendUnavailableError("regipy backend missing") from exc

        hive = RegistryHive(str(path))
        rows: list[dict[str, Any]] = []
        for plugin_cls, label in (
            (ShellBagUsrclassPlugin, "usrclass"),
            (ShellBagNtuserPlugin, "ntuser"),
        ):
            plug = plugin_cls(hive, as_json=True)
            try:
                runnable = plug.can_run()
            except Exception:
                continue
            if not runnable:
                continue
            try:
                out = plug.run()
            except ModuleNotFoundError as exc:
                raise BackendUnavailableError(
                    "shellbag PIDL decode needs libfwsi-python + libfwps-python "
                    "(regipy[full]); uv sync --all-extras"
                ) from exc
            entries = out if out is not None else getattr(plug, "entries", [])
            rows.extend(_shellbag_row(e, label) for e in (entries or []))
        return rows

    def extract_amcache_shimcache(self, path: Path) -> list[dict[str, Any]]:
        try:
            from regipy.plugins.amcache.amcache import AmCachePlugin
            from regipy.plugins.system.shimcache import ShimCachePlugin
            from regipy.registry import RegistryHive
        except ImportError as exc:  # pragma: no cover
            raise BackendUnavailableError("regipy backend missing") from exc

        hive = RegistryHive(str(path))
        fail = "amcache/shimcache decode needs regipy[full] (libfwsi+libfwps); uv sync --all-extras"
        rows: list[dict[str, Any]] = []
        for e in _run_regipy_plugin(AmCachePlugin(hive, as_json=True), fail):
            rows.append(
                {
                    "kind": "amcache",
                    "path": e.get("full_path"),
                    "sha1": e.get("sha1"),
                    "program_id": e.get("program_id"),
                    "exec_flag": None,
                    "first_run_utc": _dt_iso(e.get("timestamp")),
                    "modified_utc": _dt_iso(e.get("last_modified_timestamp_2")),
                }
            )
        for e in _run_regipy_plugin(ShimCachePlugin(hive, as_json=True), fail):
            rows.append(
                {
                    "kind": "shimcache",
                    "path": e.get("path"),
                    "sha1": None,
                    "program_id": None,
                    "exec_flag": e.get("exec_flag"),
                    "first_run_utc": None,
                    "modified_utc": _dt_iso(e.get("last_mod_date")),
                }
            )
        return rows

    def parse_usnjrnl(self, path: Path, *, max_records: int = 500_000) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        chunk_size = 1 << 20
        buf = b""
        eof = False
        with path.open("rb") as fh:
            while True:
                if len(buf) < 65536 and not eof:
                    more = fh.read(chunk_size)
                    if more:
                        buf += more
                    else:
                        eof = True
                if len(buf) < 4:
                    break
                zeros = len(buf) - len(buf.lstrip(b"\x00"))
                if zeros >= 8:
                    buf = buf[zeros - (zeros % 8) :]
                    if len(buf) < 60 and eof:
                        break
                    continue
                rec_len = int.from_bytes(buf[0:4], "little")
                if rec_len == 0:
                    buf = buf[8:]
                    continue
                if rec_len < 60 or rec_len > 0x10000:
                    buf = buf[8:]
                    continue
                if len(buf) < rec_len:
                    if eof:
                        break
                    continue
                rec, buf = buf[:rec_len], buf[rec_len:]
                if int.from_bytes(rec[4:6], "little") != 2:
                    continue
                name_len = int.from_bytes(rec[56:58], "little")
                name_off = int.from_bytes(rec[58:60], "little")
                name = ""
                if name_len > 0 and name_off + name_len <= rec_len:
                    name = rec[name_off : name_off + name_len].decode("utf-16-le", "ignore")
                rows.append(
                    {
                        "usn": int.from_bytes(rec[24:32], "little"),
                        "timestamp_utc": _filetime_iso(int.from_bytes(rec[32:40], "little")),
                        "file_name": name,
                        "reason": _decode_usn_reason(int.from_bytes(rec[40:44], "little")),
                        "file_attributes": int.from_bytes(rec[52:56], "little"),
                        "file_reference": int.from_bytes(rec[8:16], "little"),
                        "parent_reference": int.from_bytes(rec[16:24], "little"),
                    }
                )
                if len(rows) >= max_records:
                    break
        return rows

    def parse_mft(self, path: Path) -> list[dict[str, Any]]:
        try:
            from mft import PyMftParser
        except ImportError as exc:  # pragma: no cover
            raise BackendUnavailableError(
                "MFT backend missing: run `siftmesh doctor --setup`"
            ) from exc

        rows: list[dict[str, Any]] = []
        parser = PyMftParser(str(path))
        for entry in parser.entries_json():
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
