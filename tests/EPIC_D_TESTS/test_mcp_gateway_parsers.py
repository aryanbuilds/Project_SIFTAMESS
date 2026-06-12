"""Epic D parser tools against REAL upstream sample fixtures (D5-D8).

Real input -> real output. Fixtures come from the parser libraries' own public test
suites (see tests/fixtures/forensic/README.md), never SANS evidence.
"""

from __future__ import annotations

import lzma
import shutil
from pathlib import Path

import pytest
from siftmesh_core.ledgers.tool_call_ledger import read_tool_results
from siftmesh_core.mcp_gateway.backends import BackendUnavailableError, get_backend
from siftmesh_core.mcp_gateway.tools.evtx_tools import parse_evtx_powershell, parse_evtx_security
from siftmesh_core.mcp_gateway.tools.mft_tools import parse_mft_filesystem
from siftmesh_core.mcp_gateway.tools.prefetch_tools import analyze_prefetch
from siftmesh_core.mcp_gateway.tools.registry_tools import extract_registry_run_keys
from siftmesh_core.mcp_gateway.tools.timeline_tools import build_timeline
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
    """Criterion 4: the local real backend is 100% in-process — it spawns no subprocess."""
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
