"""B9: chain-of-custody ledger — validated append + re-hash verification."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from siftmesh_core.evidence.hash_utils import sha256_file
from siftmesh_core.ledgers.custody_ledger import record_ingest, verify_unchanged
from siftmesh_core.run_dir import new_run_dir

_T = datetime(2026, 1, 1, tzinfo=UTC)


def test_record_ingest_appends_validated_event(tmp_path: Path) -> None:
    rp = new_run_dir(base=tmp_path / "runs")
    record_ingest(
        rp.root,
        run_id=rp.run_id,
        artifact="a.evtx",
        source_sha256="a" * 64,
        start_time_utc=_T,
        end_time_utc=_T,
    )
    lines = rp.custody_log.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["event_type"] == "evidence_ingested"
    assert record["source_sha256"] == "a" * 64
    assert record["actor"] == "siftmesh"
    assert record["start_time_utc"].endswith("Z")


def test_verify_unchanged_detects_match_and_mismatch(tmp_path: Path) -> None:
    rp = new_run_dir(base=tmp_path / "runs")
    src = tmp_path / "orig.bin"
    src.write_bytes(b"evidence")
    baseline = sha256_file(src)

    assert verify_unchanged(
        rp.root, run_id=rp.run_id, artifact="orig.bin", baseline_sha256=baseline, source_path=src
    )
    src.write_bytes(b"tampered!")  # external change
    assert not verify_unchanged(
        rp.root, run_id=rp.run_id, artifact="orig.bin", baseline_sha256=baseline, source_path=src
    )

    results = [
        json.loads(line)["result"]
        for line in rp.custody_log.read_text(encoding="utf-8").splitlines()
    ]
    assert results == ["ok", "mismatch"]
