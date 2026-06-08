"""SIFT-lane backend (D12): EZ-Tool JSON → RealBackend row shapes, fail-closed, fixed-argv.

EZ Tools are not invoked here — ``subprocess.run`` is mocked to write synthetic (golden) EZ-tool
JSON output, so the normalization + safety contract is tested in CI without EZ Tools or evidence.
Real EZ-Tool validation against the ROCBA artifacts is human-gated on the SIFT box.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from siftmesh_core.mcp_gateway.backends import BackendUnavailableError
from siftmesh_core.mcp_gateway.backends import sift_lane as sl

# Synthetic EZ-tool JSONL output (shapes confirmed against real EvtxECmd/MFTECmd/RECmd runs).
_EVTX_ROWS = [
    {
        "EventId": 4624,
        "Channel": "Security",
        "Computer": "SRL-FORGE",
        "Provider": "Microsoft-Windows-Security-Auditing",
        "TimeCreated": "2020-11-16T03:05:00.0000000+00:00",
        "EventRecordId": "7",
        "Payload": json.dumps(
            {"EventData": {"Data": [{"@Name": "TargetUserName", "#text": "fredr"}]}}
        ),
    },
    {
        "EventId": 4625,
        "Channel": "Security",
        "Computer": "SRL-FORGE",
        "Provider": "Microsoft-Windows-Security-Auditing",
        "TimeCreated": "2020-11-16T03:06:00.0000000+00:00",
        "EventRecordId": "8",
        "Payload": "",
    },
]
_MFT_ROWS = [
    {
        "EntryNumber": 0,
        "FileName": "$MFT",
        "FileSize": 490995712,
        "IsDirectory": False,
        "Created0x10": "2016-02-12T01:23:34.8990545+00:00",
        "LastModified0x10": "2016-02-12T01:23:34.8990545+00:00",
        "LastAccess0x10": "2016-02-12T01:23:34.8990545+00:00",
    }
]
_RECMD_ROWS = [
    {
        "KeyPath": "ROOT\\Microsoft\\Windows\\CurrentVersion\\Run",
        "ValueName": "SecurityHealth",
        "ValueData": "%windir%\\system32\\SecurityHealthSystray.exe",
        "ValueType": "RegExpandSz",
    }
]

_GOLDEN = {
    "EvtxECmd.dll": "﻿" + "\n".join(json.dumps(r) for r in _EVTX_ROWS),  # BOM like real
    "MFTECmd.dll": "\n".join(json.dumps(r) for r in _MFT_ROWS),
    "RECmd.dll": "\n".join(json.dumps(r) for r in _RECMD_ROWS),
}


def _ez_dir(tmp_path: Path) -> Path:
    """Create a fake EZ Tools dir with the expected DLL layout (empty files)."""
    root = tmp_path / "ez"
    for parts in (("EvtxeCmd", "EvtxECmd.dll"), ("MFTECmd.dll",), ("RECmd", "RECmd.dll")):
        dll = root.joinpath(*parts)
        dll.parent.mkdir(parents=True, exist_ok=True)
        dll.write_text("", encoding="utf-8")
    return root


def _patch(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """Mock dotnet + subprocess to write matching golden output; return the argvs seen."""
    seen: list[list[str]] = []
    monkeypatch.setattr(sl.shutil, "which", lambda name: "/usr/bin/dotnet")

    class _P:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(argv: list[str], **kwargs: object) -> _P:
        seen.append(argv)
        assert "shell" not in kwargs  # never shell=True
        dll = Path(argv[1]).name
        out_dir = Path(argv[argv.index("--json") + 1])
        out_name = argv[argv.index("--jsonf") + 1]
        (out_dir / out_name).write_text(_GOLDEN.get(dll, ""), encoding="utf-8")
        return _P()

    monkeypatch.setattr(sl.subprocess, "run", fake_run)
    return seen


def test_parse_evtx_normalizes_and_filters(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    seen = _patch(monkeypatch)
    backend = sl.SiftLaneBackend(ez_tools_dir=_ez_dir(tmp_path))

    rows = backend.parse_evtx(Path("/ev/Security.evtx"))
    assert [r["event_id"] for r in rows] == [4624, 4625]
    r0 = rows[0]
    assert r0["channel"] == "Security" and r0["computer"] == "SRL-FORGE"
    assert r0["event_record_id"] == 7 and r0["provider"].startswith("Microsoft-Windows")
    assert r0["event_data"] == {"Data": [{"@Name": "TargetUserName", "#text": "fredr"}]}
    assert set(r0) == {  # exact RealBackend row shape
        "event_record_id",
        "event_id",
        "channel",
        "computer",
        "timestamp_utc",
        "provider",
        "event_data",
    }
    # argv is a list (fixed-argv), no shell.
    assert isinstance(seen[0], list) and seen[0][0] == "/usr/bin/dotnet"

    # filters apply post-parse (parity with RealBackend).
    only = backend.parse_evtx(Path("/ev/Security.evtx"), event_id_filter=frozenset({4625}))
    assert [r["event_id"] for r in only] == [4625]
    none = backend.parse_evtx(Path("/ev/Security.evtx"), channel_filter=frozenset({"System"}))
    assert none == []


def test_parse_mft_normalizes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _patch(monkeypatch)
    rows = sl.SiftLaneBackend(ez_tools_dir=_ez_dir(tmp_path)).parse_mft(Path("/ev/MFT"))
    assert rows[0]["record_number"] == 0 and rows[0]["name"] == "$MFT"
    assert rows[0]["logical_size"] == 490995712 and rows[0]["is_directory"] is False
    assert set(rows[0]) == {
        "record_number",
        "name",
        "logical_size",
        "is_directory",
        "si_created",
        "si_modified",
        "si_accessed",
    }


def test_extract_run_keys_normalizes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _patch(monkeypatch)
    rows = sl.SiftLaneBackend(ez_tools_dir=_ez_dir(tmp_path)).extract_run_keys(Path("/ev/SOFTWARE"))
    assert rows[0]["name"] == "SecurityHealth"
    assert rows[0]["key_path"] == "Microsoft\\Windows\\CurrentVersion\\Run"  # ROOT\\ stripped
    assert rows[0]["value"].endswith("SecurityHealthSystray.exe")
    assert set(rows[0]) == {"key_path", "name", "value", "value_type"}


def test_prefetch_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(BackendUnavailableError, match="PECmd"):
        sl.SiftLaneBackend(ez_tools_dir=_ez_dir(tmp_path)).analyze_prefetch(Path("/ev/x.pf"))


def test_missing_dll_fails_closed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(sl.shutil, "which", lambda name: "/usr/bin/dotnet")
    backend = sl.SiftLaneBackend(ez_tools_dir=tmp_path / "no_ez")  # no DLLs
    with pytest.raises(BackendUnavailableError):
        backend.parse_evtx(Path("/ev/Security.evtx"))


def test_nonzero_exit_raises(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(sl.shutil, "which", lambda name: "/usr/bin/dotnet")

    class _P:
        returncode = 1
        stdout = ""
        stderr = "boom"

    monkeypatch.setattr(sl.subprocess, "run", lambda argv, **k: _P())
    with pytest.raises(RuntimeError, match="boom"):
        sl.SiftLaneBackend(ez_tools_dir=_ez_dir(tmp_path)).parse_mft(Path("/ev/MFT"))
