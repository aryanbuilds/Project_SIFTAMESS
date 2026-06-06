"""B3: read-only posture record."""

from __future__ import annotations

import json
from pathlib import Path

from siftmesh_core.evidence.readonly import write_readonly_record
from siftmesh_core.run_dir import new_run_dir


def test_readonly_record_written(tmp_path: Path) -> None:
    evi = tmp_path / "evidence_src"
    evi.mkdir()
    (evi / "a.txt").write_text("x")
    rp = new_run_dir(base=tmp_path / "runs")
    write_readonly_record(evi, rp.root, file_count=1)

    assert rp.readonly_mounts.exists()
    data = json.loads(rp.readonly_mounts.read_text(encoding="utf-8"))
    assert data["enforcement"] == "posture_only"  # not OS-level RO-mount
    assert data["sources"][0]["access"] == "read_only"
    assert data["sources"][0]["file_count"] == 1
