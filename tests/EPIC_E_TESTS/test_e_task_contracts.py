"""E6 (task-contract generation) + E7 (windows_initial_triage template, byte-stable)."""

from __future__ import annotations

from collections.abc import Callable

from siftmesh_core.config import load_settings
from siftmesh_core.orchestrator.planner import generate_plan
from siftmesh_core.run_dir import RunPaths
from siftmesh_core.schemas.evidence import EvidenceManifest
from siftmesh_core.schemas.task import TaskContract
from siftmesh_core.schemas.yaml_io import read_yaml_model

SyntheticRun = Callable[..., RunPaths]


def _contracts(run) -> list[TaskContract]:  # type: ignore[no-untyped-def]
    return [read_yaml_model(TaskContract, p) for p in sorted(run.tasks.glob("TASK-*.yaml"))]


def test_each_task_validates_and_is_run_scoped(synthetic_run: SyntheticRun) -> None:
    run = synthetic_run()
    generate_plan(run, settings=load_settings())
    contracts = _contracts(run)
    assert len(contracts) >= 2
    for c in contracts:
        assert c.safety_policy.evidence_is_hostile is True
        assert c.safety_policy.write_allowed_only_under == ["results/", "claims/"]
        assert c.output_required == [f"results/{c.task_id}.result.json"]


def test_allowed_tools_scoped_one_per_task(synthetic_run: SyntheticRun) -> None:
    run = synthetic_run()
    generate_plan(run, settings=load_settings())
    for c in _contracts(run):
        assert len(c.allowed_tools) == 1  # each task carries exactly its single tool


def test_input_artifact_comes_from_manifest(synthetic_run: SyntheticRun) -> None:
    run = synthetic_run()
    generate_plan(run, settings=load_settings())
    manifest = EvidenceManifest.model_validate_json(run.evidence_manifest.read_text("utf-8"))
    by_path = {f.path: f.sha256 for f in manifest.files}
    for c in _contracts(run):
        for art in c.input_artifacts:
            assert art.mode == "read_only"
            assert by_path[art.path] == art.sha256  # path+hash straight from the manifest


def test_fixed_mapping_windows_initial_triage(synthetic_run: SyntheticRun) -> None:
    run = synthetic_run()
    generate_plan(run, settings=load_settings())
    tool_for = {
        c.input_artifacts[0].path: c.allowed_tools[0]
        for c in _contracts(run)
        if c.role != "timeline_executor"
    }
    assert tool_for["Security.evtx"] == "parse_evtx_security"
    assert tool_for["Microsoft-Windows-PowerShell%4Operational.evtx"] == "parse_evtx_powershell"
    assert tool_for["CMD.EXE-12345678.pf"] == "analyze_prefetch"
    assert tool_for["Users/alice/NTUSER.DAT"] == "extract_registry_run_keys"


def test_duplicate_basenames_yield_distinct_tasks(synthetic_run: SyntheticRun) -> None:
    run = synthetic_run()
    generate_plan(run, settings=load_settings())
    reg_paths = {
        c.input_artifacts[0].path
        for c in _contracts(run)
        if c.allowed_tools == ["extract_registry_run_keys"]
    }
    assert {"Users/alice/NTUSER.DAT", "Users/bob/NTUSER.DAT"} <= reg_paths


def test_plan_is_byte_stable_per_manifest(synthetic_run: SyntheticRun) -> None:
    run = synthetic_run()
    r1 = generate_plan(run, settings=load_settings())
    snap1 = {p.name: p.read_bytes() for p in (*r1.context_files, *r1.task_files)}
    r2 = generate_plan(run, settings=load_settings())
    snap2 = {p.name: p.read_bytes() for p in (*r2.context_files, *r2.task_files)}
    assert snap1 == snap2  # orchestration_events.jsonl (timestamps) is excluded by design
