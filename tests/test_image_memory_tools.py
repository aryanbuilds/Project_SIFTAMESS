"""Tool-level tests for the two governed Epic-D-deepening tools (image + memory).

The underlying TSK/7z/vol subprocesses are stubbed; these assert the audited-execution
contract: provenance line, derived-artifact chain, fail-closed, and graceful error status.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from siftmesh_core.evidence import image_access
from siftmesh_core.evidence.hash_utils import sha256_file
from siftmesh_core.ledgers.tool_call_ledger import read_tool_results
from siftmesh_core.mcp_gateway.backends import BackendUnavailableError
from siftmesh_core.mcp_gateway.tools import memory_tools
from siftmesh_core.mcp_gateway.tools.image_tools import extract_artifacts_from_image
from siftmesh_core.mcp_gateway.tools.memory_tools import analyze_memory
from siftmesh_core.run_dir import new_run_dir

_VOL_ROWS: dict[str, list[dict[str, object]]] = {
    "windows.info": [{"Variable": "Kernel Base", "Value": "0xf80000000000"}],
    "windows.pslist": [
        {"PID": 4, "PPID": 0, "ImageFileName": "System", "CreateTime": "2026", "ExitTime": None}
    ],
    "windows.pstree": [{"PID": 520, "PPID": 4, "ImageFileName": "smss.exe"}],
    "windows.netscan": [
        {
            "Proto": "TCPv4",
            "LocalAddr": "10.0.0.5",
            "LocalPort": 49512,
            "ForeignAddr": "185.1.2.3",
            "ForeignPort": 443,
            "State": "ESTABLISHED",
            "PID": 1337,
            "Owner": "evil.exe",
        }
    ],
    "windows.cmdline": [{"PID": 1337, "Process": "evil.exe", "Args": "evil.exe -enc ZQ=="}],
    "windows.malfind": [
        {"PID": 1337, "Process": "evil.exe", "Protection": "RWX", "Notes": "MZ header"}
    ],
}


def test_extract_artifacts_from_image_audited(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    (evidence / "rocba.e01").write_bytes(b"fake-ewf-image-bytes")
    run = new_run_dir(base=tmp_path / "case_runs")

    monkeypatch.setattr(image_access, "resolve_offset", lambda image: 0)
    monkeypatch.setattr(image_access, "list_partitions", lambda image: [])

    def fake_extract(image: Path, *, dest_dir: Path, offset: int, keys: object) -> list[object]:
        dest_dir.mkdir(parents=True, exist_ok=True)
        out = dest_dir / "Security.evtx"
        out.write_bytes(b"REAL-EXTRACTED-EVTX")
        return [
            image_access.ExtractedFile(
                key="security_evtx",
                ntfs_path="/Windows/System32/winevt/Logs/Security.evtx",
                inode="65-128-1",
                dest=out,
                sha256=sha256_file(out),
                size_bytes=out.stat().st_size,
            )
        ]

    monkeypatch.setattr(image_access, "extract_artifacts", fake_extract)

    result = extract_artifacts_from_image(
        run.root, image_artifact="rocba.e01", evidence_root=evidence
    )
    assert result.status == "success"
    assert result.extracted_count == 1
    assert result.backend == "sift_lane"
    assert result.tool_name == "extract_artifacts_from_image"

    # The extracted file landed under the run dir, hashed.
    extracted = run.root / "evidence" / "extracted" / "Security.evtx"
    assert extracted.is_file()

    # Exactly one provenance line, success.
    calls = read_tool_results(run.root)
    assert len(calls) == 1 and calls[0].status == "success"

    # Derived registry chains the extracted file back to the image with extraction provenance.
    derived = json.loads((run.root / "evidence" / "derived_artifacts.json").read_text())["derived"]
    chained = [d for d in derived if d.get("extraction_method") == "sleuthkit_icat"]
    assert chained and chained[0]["source_artifact"] == "rocba.e01"
    assert chained[0]["extraction_source_path"].endswith("Security.evtx")


def test_extract_artifacts_fails_closed_without_tsk(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    (evidence / "rocba.e01").write_bytes(b"fake")
    run = new_run_dir(base=tmp_path / "case_runs")

    monkeypatch.setattr(image_access, "resolve_offset", lambda image: 0)
    monkeypatch.setattr(image_access, "list_partitions", lambda image: [])

    def boom(*a: object, **k: object) -> list[object]:
        raise BackendUnavailableError("sleuthkit missing")

    monkeypatch.setattr(image_access, "extract_artifacts", boom)
    with pytest.raises(BackendUnavailableError):
        extract_artifacts_from_image(run.root, image_artifact="rocba.e01", evidence_root=evidence)
    # The failure was still recorded (status=error) before re-raising.
    calls = read_tool_results(run.root)
    assert len(calls) == 1 and calls[0].status == "error"
    assert calls[0].error_code == "backend_unavailable"


def _patch_vol(monkeypatch: pytest.MonkeyPatch, *, info_rc: int = 0) -> None:
    monkeypatch.setattr(memory_tools.shutil, "which", lambda name: "/bin/sh")  # exists

    class _P:
        def __init__(self, returncode: int, stdout: str) -> None:
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = ""

    def fake_run(argv: list[str], **kwargs: object) -> _P:
        plugin = argv[-1]
        if plugin == "windows.info":
            return _P(info_rc, json.dumps(_VOL_ROWS["windows.info"]) if info_rc == 0 else "")
        return _P(0, json.dumps(_VOL_ROWS.get(plugin, [])))

    monkeypatch.setattr(memory_tools.subprocess, "run", fake_run)


def test_analyze_memory_success(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    evidence = tmp_path / "extracted"
    evidence.mkdir()
    (evidence / "rocba.mem").write_bytes(b"PAGEDU64" + b"\x00" * 64)
    run = new_run_dir(base=tmp_path / "case_runs")
    _patch_vol(monkeypatch)

    result = analyze_memory(
        run.root,
        memory_artifact="rocba.mem",
        evidence_root=evidence,
        plugins=["pslist", "pstree", "netscan", "cmdline", "malfind"],
    )
    assert result.status == "success"
    assert result.backend == "sift_lane"
    assert result.memory_format == "windows_crashdump64"
    assert result.process_count == 1
    assert result.processes[0]["name"] == "System"
    assert result.network[0]["foreign_addr"] == "185.1.2.3"
    assert result.suspicious[0]["pid"] == 1337
    assert "windows.info" in result.plugins_ran

    # Raw Volatility JSON preserved as the tool's raw_output_path.
    assert result.raw_output_path is not None
    assert (run.root / result.raw_output_path).is_file()
    calls = read_tool_results(run.root)
    assert len(calls) == 1 and calls[0].raw_output_path == result.raw_output_path


def test_analyze_memory_fails_closed_without_vol(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    evidence = tmp_path / "extracted"
    evidence.mkdir()
    (evidence / "rocba.mem").write_bytes(b"\x00" * 64)
    run = new_run_dir(base=tmp_path / "case_runs")
    monkeypatch.setattr(memory_tools.shutil, "which", lambda name: None)
    with pytest.raises(BackendUnavailableError):
        analyze_memory(run.root, memory_artifact="rocba.mem", evidence_root=evidence, vol_path=None)


def test_analyze_memory_symbol_failure_is_error_not_fake(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    evidence = tmp_path / "extracted"
    evidence.mkdir()
    (evidence / "rocba.mem").write_bytes(b"\x00" * 64)
    run = new_run_dir(base=tmp_path / "case_runs")
    _patch_vol(monkeypatch, info_rc=1)  # symbols unresolved
    result = analyze_memory(run.root, memory_artifact="rocba.mem", evidence_root=evidence)
    assert result.status == "error"
    assert result.error_code == "vol_symbol_resolution_failed"
    assert result.process_count == 0  # no fabricated rows
