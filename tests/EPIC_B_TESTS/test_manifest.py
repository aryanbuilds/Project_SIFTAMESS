"""B4: evidence manifest + sha256sum-compatible hashes file."""

from __future__ import annotations

import hashlib
from pathlib import Path

from siftmesh_core.evidence.manifest import (
    build_manifest_from_dir,
    guess_evidence_type,
    write_hashes_sha256,
    write_manifest,
)
from siftmesh_core.run_dir import new_run_dir
from siftmesh_core.schemas.evidence import EvidenceManifest


def _evidence(tmp_path: Path) -> Path:
    evi = tmp_path / "evidence_src"
    evi.mkdir()
    (evi / "a.txt").write_text("alpha")
    logs = evi / "logs"
    logs.mkdir()
    (logs / "system.evtx").write_bytes(b"EVTX\x00data")
    return evi


def test_manifest_built_and_validates(tmp_path: Path) -> None:
    evi = _evidence(tmp_path)
    manifest = build_manifest_from_dir(evi, case_id="case01", run_id="RUN-X")
    assert isinstance(manifest, EvidenceManifest)
    assert {f.path for f in manifest.files} == {"a.txt", "logs/system.evtx"}
    evtx = next(f for f in manifest.files if f.path.endswith("evtx"))
    assert evtx.evidence_type == "evtx"


def test_write_manifest_roundtrips(tmp_path: Path) -> None:
    evi = _evidence(tmp_path)
    rp = new_run_dir(base=tmp_path / "runs")
    manifest = build_manifest_from_dir(evi, case_id="c", run_id=rp.run_id)
    write_manifest(manifest, rp.root, evidence_root=evi)
    assert rp.evidence_manifest.exists()
    loaded = EvidenceManifest.model_validate_json(rp.evidence_manifest.read_text(encoding="utf-8"))
    assert loaded == manifest


def test_hashes_sha256_format(tmp_path: Path) -> None:
    evi = _evidence(tmp_path)
    rp = new_run_dir(base=tmp_path / "runs")
    manifest = build_manifest_from_dir(evi, case_id="c", run_id=rp.run_id)
    write_hashes_sha256(manifest, rp.root, evidence_root=evi)
    assert rp.hashes_sha256.exists()
    raw = rp.hashes_sha256.read_bytes()
    assert b"\r\n" not in raw  # LF only — required for sha256sum -c on Linux
    lines = rp.hashes_sha256.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    golden = hashlib.sha256((evi / "a.txt").read_bytes()).hexdigest() + "  a.txt"
    assert golden in lines
    for line in lines:
        assert line[64:66] == "  "  # exactly two spaces (text mode)


def test_guess_evidence_type() -> None:
    assert guess_evidence_type("x/SYSTEM") == "registry"
    assert guess_evidence_type("a.zip") == "archive"
    assert guess_evidence_type("img.E01") == "disk_image"
    assert guess_evidence_type("weird.xyz") == "unknown"
