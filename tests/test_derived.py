"""B5: derived-artifacts registry."""

from __future__ import annotations

import json
from pathlib import Path

from siftmesh_core.evidence.derived import DerivedArtifact, append_derived, init_registry
from siftmesh_core.run_dir import new_run_dir


def test_registry_initialised_empty(tmp_path: Path) -> None:
    rp = new_run_dir(base=tmp_path / "runs")
    init_registry(rp.root)
    assert rp.derived_artifacts.exists()
    assert json.loads(rp.derived_artifacts.read_text(encoding="utf-8")) == {"derived": []}


def test_append_records_provenance(tmp_path: Path) -> None:
    rp = new_run_dir(base=tmp_path / "runs")
    append_derived(
        rp.root,
        DerivedArtifact(
            derived_path="results/timeline.json",
            source_artifact="logs/system.evtx",
            source_sha256="a" * 64,
            tool_call_id="TOOL-001",
        ),
    )
    data = json.loads(rp.derived_artifacts.read_text(encoding="utf-8"))
    assert len(data["derived"]) == 1
    record = data["derived"][0]
    assert record["source_artifact"] == "logs/system.evtx"
    assert record["source_sha256"] == "a" * 64
    assert record["tool_call_id"] == "TOOL-001"
