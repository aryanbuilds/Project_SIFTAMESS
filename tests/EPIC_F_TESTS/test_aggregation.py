"""Per-family task aggregation (bd 1xy6): many same-family artifacts → ONE task; the floor runs
the tool once per artifact and merges + renumbers claims, keeping per-artifact tool-call provenance.
Public fixtures only.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from siftmesh_core.config import load_settings
from siftmesh_core.evidence.manifest import build_manifest_from_dir, write_manifest
from siftmesh_core.evidence.readonly import write_readonly_record
from siftmesh_core.orchestrator.planner import generate_plan, group_actionable
from siftmesh_core.orchestrator.scheduler import dispatch_run
from siftmesh_core.run_dir import new_run_dir
from siftmesh_core.schemas.task import TaskContract
from siftmesh_core.schemas.task_result import TaskResult
from siftmesh_core.schemas.yaml_io import read_yaml_model

FORENSIC = Path(__file__).resolve().parents[1] / "fixtures" / "forensic"


def test_floor_aggregates_same_family_into_one_task(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    src = FORENSIC / "prefetch_vista_cmd.pf"
    shutil.copy(src, evidence / "CMD.EXE-AAAAAAAA.pf")
    shutil.copy(src, evidence / "NOTEPAD.EXE-BBBBBBBB.pf")
    shutil.copy(src, evidence / "ZOOM.EXE-CCCCCCCC.pf")

    run = new_run_dir(base=tmp_path / "case_runs")
    manifest = build_manifest_from_dir(evidence, case_id="agg", run_id=run.run_id)
    write_manifest(manifest, run.root, evidence_root=evidence)
    write_readonly_record(evidence, run.root, file_count=len(manifest.files))
    generate_plan(run, settings=load_settings())

    contracts = [read_yaml_model(TaskContract, p) for p in sorted(run.tasks.glob("TASK-*.yaml"))]
    pf = [c for c in contracts if c.allowed_tools == ["analyze_prefetch"]]
    assert len(pf) == 1  # 3 .pf → ONE aggregated prefetch task (not 3)
    assert len(pf[0].input_artifacts) == 3

    dispatch_run(run, settings=load_settings(), evidence_override=evidence)
    result = TaskResult.model_validate_json(run.result_path(pf[0].task_id).read_text("utf-8"))
    assert result.status == "success"
    assert len(result.tool_call_ids) == 3  # one audited analyze_prefetch call per artifact
    ids = [c.claim_id for c in result.claims]
    assert len(ids) == len(set(ids))  # claim_ids renumbered unique across artifacts
    assert {c.source_artifact for c in result.claims} == {
        "CMD.EXE-AAAAAAAA.pf",
        "NOTEPAD.EXE-BBBBBBBB.pf",
        "ZOOM.EXE-CCCCCCCC.pf",
    }


def test_group_actionable_chunks_by_cap() -> None:
    from siftmesh_core.orchestrator.artifact_router import RoutedArtifact

    arts = [
        RoutedArtifact(
            path=f"P{i}.pf",
            sha256="a" * 64,
            family="prefetch",
            tool="analyze_prefetch",
            timeline_kind="prefetch",
            objective="x",
            actionable=True,
        )
        for i in range(150)
    ]
    groups = group_actionable(arts, max_per_task=64)
    assert [len(g) for g in groups] == [64, 64, 22]  # chunked, order preserved
