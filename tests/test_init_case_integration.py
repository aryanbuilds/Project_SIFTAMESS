"""B7: init-case wires the whole vault — files, custody, evidence-unchanged."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest
import typer
from siftmesh_core.evidence.hash_utils import walk_files
from siftmesh_core.evidence.path_policy import PathPolicyViolation
from siftmesh_core.evidence.vault import init_case
from siftmesh_core.run_dir import RunPaths
from siftmesh_core.schemas.evidence import EvidenceManifest
from typer.testing import CliRunner


def _evidence(tmp_path: Path) -> Path:
    evi = tmp_path / "evidence_src"
    evi.mkdir()
    (evi / "a.txt").write_text("alpha")
    (evi / "b.log").write_text("log line")
    win = evi / "win"
    win.mkdir()
    (win / "system.evtx").write_bytes(b"EVTX\x00\x01")
    with zipfile.ZipFile(evi / "bundle.zip", "w") as zf:  # hashed as ONE entry
        zf.writestr("inner1.txt", "x")
        zf.writestr("inner2.txt", "y")
    return evi


def test_init_case_creates_all_run_files(tmp_path: Path) -> None:
    rp = init_case(tmp_path / "case01", _evidence(tmp_path))
    assert isinstance(rp, RunPaths)
    for path in (
        rp.evidence_manifest,
        rp.hashes_sha256,
        rp.readonly_mounts,
        rp.derived_artifacts,
        rp.custody_log,
        rp.orchestration_events,
        rp.evidence_policy,
    ):
        assert path.exists(), f"missing {path}"


def test_cli_init_case_produces_valid_manifest(
    runner: CliRunner, cli_app: typer.Typer, tmp_path: Path
) -> None:
    evi = _evidence(tmp_path)
    case = tmp_path / "case01"
    result = runner.invoke(cli_app, ["init-case", str(case), "--evidence", str(evi)])
    assert result.exit_code == 0, result.output
    runs = list((case / "case_runs").glob("RUN-*"))
    assert len(runs) == 1
    manifest_path = runs[0] / "evidence" / "evidence_manifest.json"
    manifest = EvidenceManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    assert {file.path for file in manifest.files} == {
        "a.txt",
        "b.log",
        "bundle.zip",
        "win/system.evtx",
    }


def test_init_case_under_case_runs(tmp_path: Path) -> None:
    case = tmp_path / "case01"
    rp = init_case(case, _evidence(tmp_path))
    runs = list((case / "case_runs").glob("RUN-*"))
    assert len(runs) == 1
    assert rp.run_id.startswith("RUN-")


def test_zip_hashed_as_single_entry(tmp_path: Path) -> None:
    rp = init_case(tmp_path / "case01", _evidence(tmp_path))
    manifest = json.loads(rp.evidence_manifest.read_text(encoding="utf-8"))
    paths = {f["path"] for f in manifest["files"]}
    assert "bundle.zip" in paths
    assert not any("inner1.txt" in p for p in paths)  # no recursion into the archive
    bundle = next(f for f in manifest["files"] if f["path"] == "bundle.zip")
    assert bundle["evidence_type"] == "archive"


def test_originals_not_modified(tmp_path: Path) -> None:
    evi = _evidence(tmp_path)
    before = {f.rel_path: f.sha256 for f in walk_files(evi)}
    init_case(tmp_path / "case01", evi)
    after = {f.rel_path: f.sha256 for f in walk_files(evi)}
    assert before == after


def test_init_case_rejects_case_dir_inside_evidence_before_writing(tmp_path: Path) -> None:
    evi = _evidence(tmp_path)
    case_inside_evidence = evi / "case01"
    with pytest.raises(PathPolicyViolation):
        init_case(case_inside_evidence, evi)
    assert not (case_inside_evidence / "case_runs").exists()


def test_custody_event_per_artifact(tmp_path: Path) -> None:
    evi = _evidence(tmp_path)
    rp = init_case(tmp_path / "case01", evi)
    events = [json.loads(line) for line in rp.custody_log.read_text(encoding="utf-8").splitlines()]
    ingested = [e for e in events if e["event_type"] == "evidence_ingested"]
    assert len(ingested) == len(walk_files(evi))


def test_orchestration_events_logged(tmp_path: Path) -> None:
    rp = init_case(tmp_path / "case01", _evidence(tmp_path))
    events = [
        json.loads(line)["event"]
        for line in rp.orchestration_events.read_text(encoding="utf-8").splitlines()
    ]
    assert "init_case_start" in events
    assert "init_case_done" in events


def test_verify_after_passes_on_clean_evidence(tmp_path: Path) -> None:
    rp = init_case(tmp_path / "case01", _evidence(tmp_path), verify_after=True)
    events = [json.loads(line) for line in rp.custody_log.read_text(encoding="utf-8").splitlines()]
    assert any(e["event_type"] == "source_rehash_verified" and e["result"] == "ok" for e in events)


def test_cli_init_case_exit_zero(runner: CliRunner, cli_app: typer.Typer, tmp_path: Path) -> None:
    evi = _evidence(tmp_path)
    result = runner.invoke(cli_app, ["init-case", str(tmp_path / "case01"), "--evidence", str(evi)])
    assert result.exit_code == 0, result.output
    assert "init-case complete" in result.output


def test_cli_init_case_missing_evidence_exit_one(
    runner: CliRunner, cli_app: typer.Typer, tmp_path: Path
) -> None:
    result = runner.invoke(
        cli_app, ["init-case", str(tmp_path / "case01"), "--evidence", str(tmp_path / "nope")]
    )
    assert result.exit_code == 1
