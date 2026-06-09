"""GAP 1 — `siftmesh decompress`: a memory archive becomes a first-class derived image.

CI-safe: the "happy path" uses a *plain* zip whose member is a fake raw image, so no real
``7z`` binary is needed. The fail-closed test forces a ``.7z`` member with ``7z`` absent.
No real forensic evidence is used.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest
import typer
from siftmesh_core.evidence import memory_access
from siftmesh_core.evidence.vault import init_case
from siftmesh_core.mcp_gateway.tools._common import resolved_source
from siftmesh_core.run_dir import RunPaths
from typer.testing import CliRunner

# A fake raw memory image: the crashdump64 magic plus padding so it is the largest file.
_FAKE_IMAGE = b"PAGEDU64" + b"\x00" * 8192


def _case_with_zip(tmp_path: Path, *, member: str, payload: bytes, zip_name: str) -> RunPaths:
    """Build an evidence dir holding one archive, then init-case over it; return the run."""
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    with zipfile.ZipFile(evidence / zip_name, "w") as zf:
        zf.writestr(member, payload)
    return init_case(tmp_path / "case", evidence)


def test_decompress_creates_derived_image_and_custody(
    runner: CliRunner, cli_app: typer.Typer, tmp_path: Path
) -> None:
    run = _case_with_zip(tmp_path, member="Rocba-Memory.raw", payload=_FAKE_IMAGE, zip_name="m.zip")

    # --evidence omitted on purpose: exercises recovery from readonly_mounts.json.
    result = runner.invoke(cli_app, ["decompress", str(run.root), "--archive", "m.zip"])
    assert result.exit_code == 0, result.output
    assert "evidence/extracted/Rocba-Memory.raw" in result.output

    image = run.evidence / "extracted" / "Rocba-Memory.raw"
    assert image.is_file()
    assert image.read_bytes() == _FAKE_IMAGE

    records = json.loads(run.derived_artifacts.read_text(encoding="utf-8"))["derived"]
    assert len(records) == 1
    rec = records[0]
    assert rec["source_artifact"] == "m.zip"
    assert rec["derived_path"] == "evidence/extracted/Rocba-Memory.raw"
    assert rec["tool_call_id"] == "DECOMP-001"
    assert len(rec["derived_sha256"]) == 64

    custody = [json.loads(line) for line in run.custody_log.read_text("utf-8").splitlines()]
    decomp_events = [e for e in custody if e["action"] == "decompress"]
    assert len(decomp_events) == 1
    assert decomp_events[0]["event_type"] == "derived_written"


def test_decompressed_image_resolves_for_analyze_memory(
    runner: CliRunner, cli_app: typer.Typer, tmp_path: Path
) -> None:
    run = _case_with_zip(tmp_path, member="cap.raw", payload=_FAKE_IMAGE, zip_name="m.zip")
    result = runner.invoke(cli_app, ["decompress", str(run.root), "--archive", "m.zip"])
    assert result.exit_code == 0, result.output

    # The GAP is closed: analyze-memory can now resolve the image (evidence_root = the run).
    path, sha = resolved_source(run.root, "evidence/extracted/cap.raw")
    assert path.is_file()
    rec = json.loads(run.derived_artifacts.read_text(encoding="utf-8"))["derived"][0]
    assert sha == rec["derived_sha256"]


def test_decompress_fails_closed_without_7z(
    runner: CliRunner, cli_app: typer.Typer, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A .7z member forces the 7z backend; with 7z absent, decompress must fail closed.
    run = _case_with_zip(
        tmp_path,
        member="Rocba-Memory.7z",
        payload=b"7z\xbc\xaf\x27\x1c" + b"\x00" * 64,
        zip_name="m.zip",
    )
    monkeypatch.setattr(memory_access.shutil, "which", lambda name: None)
    result = runner.invoke(cli_app, ["decompress", str(run.root), "--archive", "m.zip"])
    assert result.exit_code == 1
    assert "7z" in result.output  # surfaced cleanly, no fake fallback


def test_decompress_rejects_archive_outside_evidence(
    runner: CliRunner, cli_app: typer.Typer, tmp_path: Path
) -> None:
    run = _case_with_zip(tmp_path, member="cap.raw", payload=_FAKE_IMAGE, zip_name="m.zip")
    result = runner.invoke(cli_app, ["decompress", str(run.root), "--archive", "../outside.zip"])
    assert result.exit_code == 1
    assert "decompress failed" in result.output
