"""E4 — investigation_plan.yaml: parses; unique ids; executor steps map to artifacts."""

from __future__ import annotations

from collections.abc import Callable

from siftmesh_core.config import load_settings
from siftmesh_core.orchestrator.planner import generate_plan
from siftmesh_core.run_dir import RunPaths
from siftmesh_core.schemas.evidence import EvidenceManifest
from siftmesh_core.schemas.plan import InvestigationPlan
from siftmesh_core.schemas.yaml_io import read_yaml_model

SyntheticRun = Callable[..., RunPaths]


def test_plan_parses_into_model(synthetic_run: SyntheticRun) -> None:
    run = synthetic_run()
    generate_plan(run, settings=load_settings())
    plan = read_yaml_model(InvestigationPlan, run.investigation_plan)
    assert plan.template == "windows_initial_triage"
    assert plan.plan_id == run.run_id


def test_step_ids_unique(synthetic_run: SyntheticRun) -> None:
    run = synthetic_run()
    plan = generate_plan(run, settings=load_settings()).plan
    ids = [s.step_id for s in plan.steps]
    assert len(ids) == len(set(ids))


def test_executor_steps_map_to_manifest_artifacts(synthetic_run: SyntheticRun) -> None:
    run = synthetic_run()
    plan = generate_plan(run, settings=load_settings()).plan
    manifest = EvidenceManifest.model_validate_json(run.evidence_manifest.read_text("utf-8"))
    paths = {f.path for f in manifest.files}
    bound = [s for s in plan.steps if s.kind in ("executor", "timeline")]
    assert bound  # at least the executors + timeline
    for step in bound:
        assert step.input_artifact in paths
        assert step.task_id and step.tool


def test_plan_has_deep_context_critique_report(synthetic_run: SyntheticRun) -> None:
    run = synthetic_run()
    plan = generate_plan(run, settings=load_settings()).plan
    kinds = [s.kind for s in plan.steps]
    assert kinds[0] == "deep_context"
    assert "critique" in kinds and kinds[-1] == "report"
