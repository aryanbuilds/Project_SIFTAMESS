"""run_tool raw-output capture + DerivedArtifact schema backward-compatibility."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from siftmesh_core.evidence.derived import DerivedArtifact, append_derived
from siftmesh_core.ledgers.tool_call_ledger import read_tool_results
from siftmesh_core.mcp_gateway.audit_exec import _RAW_OUTPUT_KEY, _RAW_SUFFIX_KEY, run_tool
from siftmesh_core.run_dir import new_run_dir
from siftmesh_core.schemas.tool_result import ToolResult

_SHA = "0" * 64


class _RawResult(ToolResult):
    note: str = ""


def test_run_tool_captures_raw_output(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    run = new_run_dir(base=tmp_path / "case_runs")

    def produce() -> dict[str, Any]:
        return {"note": "hi", _RAW_OUTPUT_KEY: "VOL-RAW-JSON", _RAW_SUFFIX_KEY: "vol.json"}

    result = run_tool(
        run.root,
        result_cls=_RawResult,
        tool_name="t_raw",
        source_artifact="x",
        source_sha256=_SHA,
        backend="sift_lane",
        produce=produce,
        evidence_root=evidence,
    )

    assert result.note == "hi"  # sentinel keys never leak into the typed model
    assert result.raw_output_path == "results/TOOL-001.vol.json"
    raw_file = run.root / result.raw_output_path
    assert raw_file.read_text() == "VOL-RAW-JSON"
    assert (run.root / result.structured_result_path).is_file()  # type: ignore[arg-type]

    # Both the structured and raw outputs are registered as derived artifacts.
    derived = json.loads((run.root / "evidence" / "derived_artifacts.json").read_text())["derived"]
    derived_paths = {d["derived_path"] for d in derived}
    assert "results/TOOL-001.structured.json" in derived_paths
    assert "results/TOOL-001.vol.json" in derived_paths

    calls = read_tool_results(run.root)
    assert len(calls) == 1 and calls[0].raw_output_path == "results/TOOL-001.vol.json"


def test_derived_artifact_backward_compatible(tmp_path: Path) -> None:
    """Old derived_artifacts.json (no extraction_* fields) still loads + accepts new records."""
    run = new_run_dir(base=tmp_path / "case_runs")
    registry = run.root / "evidence" / "derived_artifacts.json"
    # Simulate a registry written by an earlier version (no extraction provenance fields).
    legacy = {
        "derived": [
            {
                "derived_path": "results/TOOL-001.structured.json",
                "source_artifact": "a.evtx",
                "source_sha256": _SHA,
                "tool_call_id": "TOOL-001",
                "derived_sha256": _SHA,
            }
        ]
    }
    registry.write_text(json.dumps(legacy, indent=2) + "\n", encoding="utf-8")

    append_derived(
        run.root,
        DerivedArtifact(
            derived_path="evidence/extracted/Security.evtx",
            source_artifact="rocba.e01",
            source_sha256=_SHA,
            tool_call_id="TOOL-002",
            derived_sha256=_SHA,
            extraction_source_path="/Windows/System32/winevt/Logs/Security.evtx",
            extraction_inode="65-128-1",
            extraction_method="sleuthkit_icat",
        ),
    )

    data = json.loads(registry.read_text())["derived"]
    assert len(data) == 2
    assert "extraction_method" not in data[0]  # legacy record untouched
    assert data[1]["extraction_method"] == "sleuthkit_icat"  # new provenance recorded
