"""F1/F2 - adapter protocol + deterministic real-tool executor over real fixtures."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from siftmesh_core.adapters import get_adapter
from siftmesh_core.adapters.base import AdapterContext
from siftmesh_core.config import load_settings
from siftmesh_core.mcp_gateway.registry import ToolNotAllowedError
from siftmesh_core.orchestrator.scheduler import dispatch_run
from siftmesh_core.run_dir import RunPaths
from siftmesh_core.schemas.task import InputArtifact, SafetyPolicy, TaskContract
from siftmesh_core.schemas.task_result import TaskResult

RealCase = Callable[..., tuple[RunPaths, Path]]


def _all_claims(run: RunPaths) -> list:  # type: ignore[type-arg]
    out = []
    for p in sorted(run.results.glob("TASK-*.result.json")):
        out.extend(TaskResult.model_validate_json(p.read_text(encoding="utf-8")).claims)
    return out


def test_adapter_writes_expected_result_path(real_case: RealCase) -> None:
    run, _ = real_case()
    refs = dispatch_run(run, settings=load_settings())
    assert refs
    for ref in refs:
        assert ref.result_path == run.result_path(ref.task_id)
        assert ref.result_path.is_file()


def test_deterministic_executor_security_4625_claim_is_anchored(real_case: RealCase) -> None:
    run, _ = real_case()
    dispatch_run(run, settings=load_settings())
    claims = _all_claims(run)
    fours = [c for c in claims if "4625" in c.claim]
    assert fours, "expected a real EventID 4625 claim from security_short.evtx"
    c = fours[0]
    assert c.status == "confirmed"
    assert c.tool_call_id and c.source_sha256 and c.tool_name and c.source_artifact


def test_deterministic_executor_prefetch_run_count(real_case: RealCase) -> None:
    run, _ = real_case()
    dispatch_run(run, settings=load_settings())
    assert any("executed 3 time" in c.claim for c in _all_claims(run))


def test_deterministic_executor_registry_sidebar(real_case: RealCase) -> None:
    run, _ = real_case()
    dispatch_run(run, settings=load_settings())
    assert any("Sidebar" in c.claim for c in _all_claims(run))


def test_build_timeline_task_executes(real_case: RealCase) -> None:
    run, _ = real_case()
    dispatch_run(run, settings=load_settings())
    assert any(c.evidence_type == "timeline" for c in _all_claims(run))


def test_every_anchored_claim_has_binding(real_case: RealCase) -> None:
    run, _ = real_case()
    dispatch_run(run, settings=load_settings())
    for c in _all_claims(run):
        if c.status != "unsupported":
            assert c.tool_call_id and c.source_sha256 and c.tool_name


def test_claim_content_deterministic_across_runs(real_case: RealCase) -> None:
    # Two independent runs over identical fixtures → identical claim CONTENT (text/
    # status/confidence/evidence_type). tool_call_id/timestamps vary by run and are
    # deliberately excluded - the result file is not byte-stable, the content is.
    run_a, _ = real_case()
    run_b, _ = real_case()
    dispatch_run(run_a, settings=load_settings())
    dispatch_run(run_b, settings=load_settings())

    def content(run: RunPaths) -> set[tuple[str, str, float, str]]:
        return {(c.claim, c.status, c.confidence, c.evidence_type) for c in _all_claims(run)}

    assert content(run_a) == content(run_b)


def test_forbidden_tool_refused_by_adapter(real_case: RealCase) -> None:
    run, evidence = real_case()
    contract = TaskContract(
        task_id="TASK-999",
        role="rogue",
        objective="x",
        assigned_agent_profile="deterministic_executor",
        allowed_tools=["execute_shell_command"],  # forbidden
        input_artifacts=[InputArtifact(path="Security.evtx", sha256="a" * 64)],
        safety_policy=SafetyPolicy(),
    )
    adapter = get_adapter("deterministic_executor", settings=load_settings())
    ctx = AdapterContext(run=run, evidence_root=evidence, settings=load_settings())
    with pytest.raises(ToolNotAllowedError):
        adapter.run(contract, ctx)


def test_round_trips_task_result_yaml_shape(real_case: RealCase) -> None:
    run, _ = real_case()
    dispatch_run(run, settings=load_settings())
    for p in sorted(run.results.glob("TASK-*.result.json")):
        tr = TaskResult.model_validate_json(p.read_text(encoding="utf-8"))
        assert tr.status in ("success", "error", "retry_required")
        assert tr.tool_call_ids
