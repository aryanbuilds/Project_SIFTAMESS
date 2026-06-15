"""Epic D parser tools against REAL upstream sample fixtures (D5-D8).

Real input -> real output. Fixtures come from the parser libraries' own public test
suites (see tests/fixtures/forensic/README.md), never SANS evidence.
"""

from __future__ import annotations

import json
import lzma
import shutil
import sqlite3
from pathlib import Path

import pytest
from siftmesh_core.ledgers.tool_call_ledger import read_tool_results
from siftmesh_core.mcp_gateway.backends import BackendUnavailableError, get_backend
from siftmesh_core.mcp_gateway.tools.amcache_tools import parse_amcache_shimcache
from siftmesh_core.mcp_gateway.tools.browser_tools import parse_browser_history
from siftmesh_core.mcp_gateway.tools.evtx_tools import parse_evtx_powershell, parse_evtx_security
from siftmesh_core.mcp_gateway.tools.lnk_tools import parse_lnk_jumplists
from siftmesh_core.mcp_gateway.tools.mft_tools import parse_mft_filesystem
from siftmesh_core.mcp_gateway.tools.prefetch_tools import analyze_prefetch
from siftmesh_core.mcp_gateway.tools.recentdocs_tools import parse_recentdocs_mru
from siftmesh_core.mcp_gateway.tools.registry_tools import extract_registry_run_keys
from siftmesh_core.mcp_gateway.tools.shellbag_tools import parse_shellbags
from siftmesh_core.mcp_gateway.tools.timeline_tools import build_timeline
from siftmesh_core.mcp_gateway.tools.usb_tools import parse_usb_registry
from siftmesh_core.mcp_gateway.tools.usn_tools import parse_usnjrnl
from siftmesh_core.run_dir import RunPaths, new_run_dir

FIXTURES = Path(__file__).parent.parent / "fixtures" / "forensic"


@pytest.fixture
def case(tmp_path: Path) -> tuple[RunPaths, Path]:
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    shutil.copy(FIXTURES / "security_short.evtx", evidence / "Security.evtx")
    shutil.copy(FIXTURES / "prefetch_vista_cmd.pf", evidence / "CMD.EXE-89305D47.pf")
    shutil.copy(FIXTURES / "mft_entry_single", evidence / "$MFT")
    (evidence / "NTUSER.DAT").write_bytes(
        lzma.decompress((FIXTURES / "ntuser.dat.xz").read_bytes())
    )
    run = new_run_dir(base=tmp_path / "case_runs")
    return run, evidence


def test_real_backend_is_in_process(
    case: tuple[RunPaths, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Criterion 4: the local real backend is 100% in-process - it spawns no subprocess."""
    import subprocess

    _run, evidence = case

    def _no_subprocess(*a: object, **k: object) -> object:
        raise AssertionError("RealBackend must not spawn a subprocess (in-process only)")

    monkeypatch.setattr(subprocess, "run", _no_subprocess)
    monkeypatch.setattr(subprocess, "Popen", _no_subprocess)

    backend = get_backend("real")
    assert backend.name == "real"
    assert len(backend.parse_evtx(evidence / "Security.evtx")) == 7
    assert backend.analyze_prefetch(evidence / "CMD.EXE-89305D47.pf")["run_count"] is not None
    assert isinstance(backend.extract_run_keys(evidence / "NTUSER.DAT"), list)
    assert isinstance(backend.parse_mft(evidence / "$MFT"), list)


def test_parse_evtx_security_returns_real_records(case: tuple[RunPaths, Path]) -> None:
    run, evidence = case
    result = parse_evtx_security(run.root, source_artifact="Security.evtx", evidence_root=evidence)
    assert result.status == "success"
    assert result.event_count == 7
    assert all(e["channel"] == "Security" for e in result.events)
    assert 4625 in {e["event_id"] for e in result.events}  # a real failed-logon event


def test_evtx_event_id_filter_is_real(case: tuple[RunPaths, Path]) -> None:
    _run, evidence = case
    backend = get_backend("real")
    rows = backend.parse_evtx(
        evidence / "Security.evtx",
        event_id_filter=frozenset({4625}),
        channel_filter=frozenset({"Security"}),
    )
    assert rows  # the filter keeps real matching records...
    assert all(r["event_id"] == 4625 for r in rows)  # ...and excludes everything else


def test_evtx_channel_filter_excludes_other_channels(case: tuple[RunPaths, Path]) -> None:
    _run, evidence = case
    backend = get_backend("real")
    rows = backend.parse_evtx(
        evidence / "Security.evtx",
        channel_filter=frozenset({"Microsoft-Windows-PowerShell/Operational"}),
    )
    assert rows == []


def test_parse_evtx_powershell_excludes_non_powershell(case: tuple[RunPaths, Path]) -> None:
    run, evidence = case
    # A Security log has no 4103/4104 -> the PowerShell filter correctly yields none.
    result = parse_evtx_powershell(
        run.root, source_artifact="Security.evtx", evidence_root=evidence
    )
    assert result.status == "success"
    assert result.event_count == 0


def test_analyze_prefetch_real(case: tuple[RunPaths, Path]) -> None:
    run, evidence = case
    result = analyze_prefetch(
        run.root, source_artifact="CMD.EXE-89305D47.pf", evidence_root=evidence
    )
    assert result.status == "success"
    assert result.executable_filename == "CMD.EXE"
    assert result.run_count == 3
    assert result.last_run_times  # at least one real run timestamp


def test_parse_mft_filesystem_real(case: tuple[RunPaths, Path]) -> None:
    run, evidence = case
    result = parse_mft_filesystem(run.root, source_artifact="$MFT", evidence_root=evidence)
    assert result.status == "success"
    assert result.tool_name == "parse_mft_filesystem"
    assert result.entry_count == len(result.files) and result.entry_count >= 1
    assert result.file_count + result.directory_count == result.entry_count
    # each row carries the real metadata fields (names/sizes/SI timestamps)
    assert all("record_number" in r for r in result.files)
    # provenance line written
    ledger = read_tool_results(run.root)
    assert any(t.tool_name == "parse_mft_filesystem" for t in ledger)


def test_parse_recentdocs_mru_real(case: tuple[RunPaths, Path]) -> None:
    run, evidence = case
    result = parse_recentdocs_mru(run.root, source_artifact="NTUSER.DAT", evidence_root=evidence)
    assert result.status == "success"
    assert result.tool_name == "parse_recentdocs_mru"
    # the regipy fixture hive has a populated RecentDocs MRU → real decoded filenames
    assert result.entry_count >= 1 and result.entry_count == len(result.mru_entries)
    assert all(r.get("name") for r in result.mru_entries)  # decoded names, never empty


def test_parse_usb_registry_real(case: tuple[RunPaths, Path]) -> None:
    run, evidence = case
    result = parse_usb_registry(run.root, source_artifact="NTUSER.DAT", evidence_root=evidence)
    assert result.status == "success"
    assert result.tool_name == "parse_usb_registry"
    # the fixture NTUSER hive has MountPoints2 subkeys → mounted-volume rows
    assert result.device_count >= 1 and result.device_count == len(result.devices)
    assert any(r.get("source_key") == "MountPoints2" for r in result.devices)


def _make_chromium_history(path: Path) -> None:
    """A real (deterministic) Chrome/Edge ``History`` sqlite with one visit + one download."""
    conn = sqlite3.connect(path)
    try:
        conn.executescript(
            "CREATE TABLE urls(id INTEGER PRIMARY KEY, url TEXT, title TEXT, "
            "visit_count INTEGER, typed_count INTEGER, last_visit_time INTEGER, hidden INTEGER);"
            "CREATE TABLE downloads(id INTEGER PRIMARY KEY, target_path TEXT, tab_url TEXT, "
            "total_bytes INTEGER, start_time INTEGER);"
        )
        conn.execute(
            "INSERT INTO urls(url,title,visit_count,typed_count,last_visit_time,hidden) "
            "VALUES(?,?,?,?,?,0)",
            ("https://drive.google.com/drive/my-drive", "My Drive", 7, 3, 13350000000000000),
        )
        conn.execute(
            "INSERT INTO downloads(target_path,tab_url,total_bytes,start_time) VALUES(?,?,?,?)",
            (
                "C:\\Users\\fredr\\Downloads\\ProjectX.zip",
                "https://drive.google.com/file/abc",
                1048576,
                13350000000000000,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _make_firefox_places(path: Path) -> None:
    """A real (deterministic) Firefox ``places.sqlite`` with one visit + one download anno."""
    conn = sqlite3.connect(path)
    try:
        conn.executescript(
            "CREATE TABLE moz_places(id INTEGER PRIMARY KEY, url TEXT, title TEXT, "
            "visit_count INTEGER, last_visit_date INTEGER);"
            "CREATE TABLE moz_anno_attributes(id INTEGER PRIMARY KEY, name TEXT);"
            "CREATE TABLE moz_annos(id INTEGER PRIMARY KEY, place_id INTEGER, "
            "anno_attribute_id INTEGER, content TEXT);"
        )
        conn.execute(
            "INSERT INTO moz_places(id,url,title,visit_count,last_visit_date) VALUES(1,?,?,?,?)",
            ("https://mail.proton.me/inbox", "Proton Mail", 4, 1704164645000000),
        )
        conn.execute(
            "INSERT INTO moz_anno_attributes(id,name) VALUES(1,'downloads/destinationFileURI')"
        )
        conn.execute(
            "INSERT INTO moz_annos(id,place_id,anno_attribute_id,content) VALUES(1,1,1,?)",
            ("file:///home/fredr/Downloads/leak.7z",),
        )
        conn.commit()
    finally:
        conn.close()


def test_parse_browser_history_chromium_real(case: tuple[RunPaths, Path]) -> None:
    run, evidence = case
    _make_chromium_history(evidence / "History")
    result = parse_browser_history(run.root, source_artifact="History", evidence_root=evidence)
    assert result.status == "success"
    assert result.tool_name == "parse_browser_history"
    assert result.visit_count == 1 and result.download_count == 1
    assert result.entry_count == len(result.history) == 2
    dl = next(r for r in result.history if r["kind"] == "download")
    assert dl["target_path"].endswith("ProjectX.zip") and dl["source"] == "chromium"
    assert dl["last_visit_utc"] and dl["last_visit_utc"].endswith("Z")
    visit = next(r for r in result.history if r["kind"] == "visit")
    assert visit["url"].startswith("https://drive.google.com")


def test_parse_browser_history_firefox_real(case: tuple[RunPaths, Path]) -> None:
    run, evidence = case
    _make_firefox_places(evidence / "places.sqlite")
    result = parse_browser_history(
        run.root, source_artifact="places.sqlite", evidence_root=evidence
    )
    assert result.status == "success"
    assert result.visit_count == 1 and result.download_count == 1
    visit = next(r for r in result.history if r["kind"] == "visit")
    assert visit["source"] == "firefox" and visit["last_visit_utc"].endswith("Z")
    dl = next(r for r in result.history if r["kind"] == "download")
    assert dl["target_path"].endswith("leak.7z")


def test_parse_lnk_single_real(case: tuple[RunPaths, Path]) -> None:
    run, evidence = case
    shutil.copy(FIXTURES / "lnk_sample.lnk", evidence / "Recent.lnk")
    result = parse_lnk_jumplists(run.root, source_artifact="Recent.lnk", evidence_root=evidence)
    assert result.status == "success"
    assert result.tool_name == "parse_lnk_jumplists"
    assert result.lnk_count == 1 and result.entry_count == 1
    row = result.entries[0]
    assert row["kind"] == "lnk"
    assert str(row["target_path"]).endswith("Documents.library-ms")


def test_parse_lnk_automatic_destinations_real(case: tuple[RunPaths, Path]) -> None:
    run, evidence = case
    shutil.copy(
        FIXTURES / "jumplist_auto.automaticDestinations-ms",
        evidence / "auto.automaticDestinations-ms",
    )
    result = parse_lnk_jumplists(
        run.root, source_artifact="auto.automaticDestinations-ms", evidence_root=evidence
    )
    assert result.status == "success"
    # OLE compound -> one row per numeric LNK stream (DestList skipped), all tagged jumplist
    assert result.jumplist_count >= 1 and result.entry_count == result.jumplist_count
    assert all(r["kind"] == "jumplist" for r in result.entries)
    assert any(r["target_path"] for r in result.entries)  # at least one resolved target


def test_parse_lnk_custom_destinations_real(case: tuple[RunPaths, Path]) -> None:
    run, evidence = case
    shutil.copy(
        FIXTURES / "jumplist_custom.customDestinations-ms",
        evidence / "custom.customDestinations-ms",
    )
    result = parse_lnk_jumplists(
        run.root, source_artifact="custom.customDestinations-ms", evidence_root=evidence
    )
    assert result.status == "success"
    assert result.jumplist_count >= 1
    paths = " ".join(str(r.get("target_path") or "") for r in result.entries)
    assert "GettingStarted.exe" in paths  # real embedded LNK target


def test_parse_shellbags_usrclass_real(case: tuple[RunPaths, Path]) -> None:
    run, evidence = case
    (evidence / "UsrClass.dat").write_bytes(
        lzma.decompress((FIXTURES / "usrclass.dat.xz").read_bytes())
    )
    result = parse_shellbags(run.root, source_artifact="UsrClass.dat", evidence_root=evidence)
    assert result.status == "success"
    assert result.tool_name == "parse_shellbags"
    assert result.entry_count >= 1 and result.entry_count == len(result.entries)
    assert all(r["source_hive"] == "usrclass" for r in result.entries)
    # real PIDL decode (libfwsi/libfwps) -> reconstructed folder paths, never fabricated
    assert any(r.get("folder_path") for r in result.entries)


def test_parse_shellbags_ntuser_real(case: tuple[RunPaths, Path]) -> None:
    run, evidence = case
    (evidence / "NTUSER_BAGMRU.DAT").write_bytes(
        lzma.decompress((FIXTURES / "ntuser_bagmru.dat.xz").read_bytes())
    )
    result = parse_shellbags(run.root, source_artifact="NTUSER_BAGMRU.DAT", evidence_root=evidence)
    assert result.status == "success"
    assert result.entry_count >= 1
    assert all(r["source_hive"] == "ntuser" for r in result.entries)
    folders = " ".join(str(r.get("folder_path") or "") for r in result.entries)
    assert "wsl$" in folders  # a real decoded BagMRU folder path from the fixture


def test_parse_amcache_real(case: tuple[RunPaths, Path]) -> None:
    run, evidence = case
    (evidence / "Amcache.hve").write_bytes(
        lzma.decompress((FIXTURES / "amcache.hve.xz").read_bytes())
    )
    result = parse_amcache_shimcache(
        run.root, source_artifact="Amcache.hve", evidence_root=evidence
    )
    assert result.status == "success"
    assert result.tool_name == "parse_amcache_shimcache"
    assert result.amcache_count >= 1 and result.shimcache_count == 0
    assert result.entry_count == len(result.entries)
    row = next(r for r in result.entries if r["kind"] == "amcache")
    assert row["path"] and row["sha1"]  # real decoded program path + SHA-1


def test_parse_shimcache_from_system_real(case: tuple[RunPaths, Path]) -> None:
    run, evidence = case
    (evidence / "SYSTEM").write_bytes(lzma.decompress((FIXTURES / "system.xz").read_bytes()))
    result = parse_amcache_shimcache(run.root, source_artifact="SYSTEM", evidence_root=evidence)
    assert result.status == "success"
    assert result.shimcache_count >= 1 and result.amcache_count == 0
    assert all(r["kind"] == "shimcache" for r in result.entries)
    assert any(r.get("path") for r in result.entries)  # real AppCompatCache paths


def _usn_record(usn: int, file_ref: int, parent_ref: int, ts: int, reason: int, name: str) -> bytes:
    """One real USN_RECORD_V2 (the documented on-disk layout)."""
    name_b = name.encode("utf-16-le")
    body = b"".join(
        (
            (2).to_bytes(2, "little"),  # MajorVersion
            (0).to_bytes(2, "little"),  # MinorVersion
            file_ref.to_bytes(8, "little"),
            parent_ref.to_bytes(8, "little"),
            usn.to_bytes(8, "little"),
            ts.to_bytes(8, "little"),  # FILETIME
            reason.to_bytes(4, "little"),
            (0).to_bytes(4, "little"),  # SourceInfo
            (0).to_bytes(4, "little"),  # SecurityId
            (0x20).to_bytes(4, "little"),  # FileAttributes (ARCHIVE)
            len(name_b).to_bytes(2, "little"),
            (60).to_bytes(2, "little"),  # FileNameOffset
            name_b,
        )
    )
    rec = body + b"\x00" * ((-(len(body) + 4)) % 8)  # pad whole record to 8 bytes
    return (len(rec) + 4).to_bytes(4, "little") + rec


def _make_usn_journal(path: Path) -> None:
    """A real $J: leading sparse zeros + create/delete/rename records (real USN_RECORD_V2)."""
    ft = 131000000000000000  # a ~2016 FILETIME
    data = b"\x00" * 4096  # leading sparse (deallocated) zeros, like a real $J
    data += _usn_record(100, 0x1000, 0x5, ft, 0x100, "secret.docx")  # FILE_CREATE
    data += _usn_record(200, 0x1000, 0x5, ft + 1, 0x80000200, "secret.docx")  # FILE_DELETE+CLOSE
    data += _usn_record(300, 0x1001, 0x5, ft + 2, 0x1000, "old.txt")  # RENAME_OLD_NAME
    data += _usn_record(400, 0x1001, 0x5, ft + 3, 0x2000, "new.txt")  # RENAME_NEW_NAME
    path.write_bytes(data)


def test_parse_usnjrnl_real(case: tuple[RunPaths, Path]) -> None:
    run, evidence = case
    _make_usn_journal(evidence / "UsnJrnl.$J")
    result = parse_usnjrnl(run.root, source_artifact="UsnJrnl.$J", evidence_root=evidence)
    assert result.status == "success"
    assert result.tool_name == "parse_usnjrnl"
    assert result.entry_count == 4  # sparse zeros skipped, 4 real records parsed
    names = {r["file_name"] for r in result.entries}
    assert {"secret.docx", "old.txt", "new.txt"} <= names
    deleted = [r for r in result.entries if r["reason"] and "FILE_DELETE" in r["reason"]]
    assert deleted and deleted[0]["file_name"] == "secret.docx"  # captures the deleted file
    assert all(str(r["timestamp_utc"]).endswith("Z") for r in result.entries)


def test_parse_psort_jsonl_real(tmp_path: Path) -> None:
    # The full Plaso run is host-gated (not CI); here we test the real psort json_line parsing.
    from siftmesh_core.evidence.super_timeline import parse_psort_jsonl

    p = tmp_path / "timeline.jsonl"
    lines = [
        json.dumps(
            {
                "datetime": "2024-01-02T03:04:05+00:00",
                "timestamp_desc": "Creation Time",
                "message": "C:/Users/fredr/Downloads/ProjectX.zip",
                "source_short": "FILE",
                "parser": "filestat",
                "data_type": "fs:stat",
            }
        ),
        json.dumps(
            {
                "datetime": "2024-01-02T03:05:00+00:00",
                "message": "Run key",
                "source_short": "REG",
                "parser": "winreg",
                "data_type": "windows:registry:key_value",
            }
        ),
        "",  # blank line skipped
        "not-json",  # undecodable line skipped
    ]
    p.write_text("\n".join(lines), encoding="utf-8")
    events, total = parse_psort_jsonl(p)
    assert total == 2 and len(events) == 2
    assert events[0]["timestamp_utc"] == "2024-01-02T03:04:05+00:00"
    assert events[0]["parser"] == "filestat"
    capped, total2 = parse_psort_jsonl(p, max_events=1)
    assert total2 == 2 and len(capped) == 1  # total counted; stored list capped


def test_extract_registry_run_keys_real(case: tuple[RunPaths, Path]) -> None:
    run, evidence = case
    result = extract_registry_run_keys(
        run.root, source_artifact="NTUSER.DAT", evidence_root=evidence
    )
    assert result.status == "success"
    assert result.run_key_count >= 1
    assert "Sidebar" in {row["name"] for row in result.run_keys}  # real autostart value


def test_build_timeline_merges_and_orders(case: tuple[RunPaths, Path]) -> None:
    run, evidence = case
    result = build_timeline(
        run.root,
        inputs=[
            {"artifact": "Security.evtx", "kind": "evtx"},
            {"artifact": "CMD.EXE-89305D47.pf", "kind": "prefetch"},
            {"artifact": "$MFT", "kind": "mft"},
        ],
        evidence_root=evidence,
    )
    assert result.status == "success"
    assert result.event_count > 7  # evtx events + prefetch run(s) + mft entry
    assert len(result.sources) == 3
    kinds = {row["source_kind"] for row in result.events}
    assert {"evtx", "prefetch", "mft"} <= kinds
    stamps = [row["timestamp_utc"] for row in result.events if row["timestamp_utc"]]
    assert stamps == sorted(stamps)  # chronological order


def test_build_timeline_rejects_unknown_kind(case: tuple[RunPaths, Path]) -> None:
    run, evidence = case
    with pytest.raises(ValueError, match="unsupported timeline kind"):
        build_timeline(
            run.root,
            inputs=[{"artifact": "Security.evtx", "kind": "pcap"}],
            evidence_root=evidence,
        )


def test_parser_logs_provenance_line(case: tuple[RunPaths, Path]) -> None:
    run, evidence = case
    result = analyze_prefetch(
        run.root, source_artifact="CMD.EXE-89305D47.pf", evidence_root=evidence
    )
    ledger = read_tool_results(run.root)
    assert len(ledger) == 1
    assert ledger[0].source_artifact == "CMD.EXE-89305D47.pf"
    assert ledger[0].backend == "real"
    assert (run.root / str(result.structured_result_path)).is_file()


def test_missing_artifact_raises(case: tuple[RunPaths, Path]) -> None:
    run, evidence = case
    with pytest.raises(FileNotFoundError):
        parse_evtx_security(run.root, source_artifact="nope.evtx", evidence_root=evidence)


def test_sift_lane_backend_fails_closed_and_is_audited(
    case: tuple[RunPaths, Path], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    run, evidence = case
    # D12 wires sift_lane to EZ Tools; with the EZ Tools dir absent it fails closed (no fake)
    # and the attempt is still audited as an error (config flip via SIFTMESH_EZ_TOOLS_DIR).
    monkeypatch.setenv("SIFTMESH_EZ_TOOLS_DIR", str(tmp_path / "no_ez_tools"))
    with pytest.raises(BackendUnavailableError):
        parse_evtx_security(
            run.root,
            source_artifact="Security.evtx",
            evidence_root=evidence,
            backend_mode="sift_lane",
        )
    ledger = read_tool_results(run.root)
    assert ledger and ledger[-1].status == "error"
    assert ledger[-1].error_code == "backend_unavailable"
