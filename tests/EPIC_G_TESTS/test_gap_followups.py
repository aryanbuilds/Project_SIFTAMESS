"""G9 — coverage/corroboration gap detection + follow-up-task generation."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import typer
from siftmesh_core.config import load_settings
from siftmesh_core.ledgers.followups import read_followups
from siftmesh_core.orchestrator.critic import critique_run, detect_coverage_gaps
from siftmesh_core.orchestrator.decide import decide
from siftmesh_core.run_dir import RunPaths
from siftmesh_core.schemas.claim import Claim
from siftmesh_core.schemas.task import TaskContract
from siftmesh_core.schemas.task_result import TaskResult
from siftmesh_core.schemas.yaml_io import read_yaml_model
from typer.testing import CliRunner

DispatchedCase = Callable[..., tuple[RunPaths, Path]]
_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _registry_task(run: RunPaths) -> Path:
    for p in sorted(run.tasks.glob("TASK-*.yaml")):
        if "registry" in read_yaml_model(TaskContract, p).role:
            return p
    raise AssertionError("no registry task in the planned run")


def test_followup_task_created_for_coverage_gap(dispatched_case: DispatchedCase) -> None:
    run, _ = dispatched_case()
    gap_artifact = read_yaml_model(TaskContract, _registry_task(run)).input_artifacts[0].path
    # A hive now feeds MULTIPLE tools (run-keys + recentdocs + usb), so remove EVERY task covering
    # this artifact for it to be genuinely unexamined.
    for p in sorted(run.tasks.glob("TASK-*.yaml")):
        c = read_yaml_model(TaskContract, p)
        if any(ia.path == gap_artifact for ia in c.input_artifacts):
            p.unlink()

    assert gap_artifact in {a.path for a in detect_coverage_gaps(run)}
    critique_run(run, settings=load_settings())

    fups = read_followups(run.root)
    assert any(f.reason == "coverage_gap" and f.artifact == gap_artifact for f in fups)
    # the follow-up is a real, valid task contract covering the gap artifact
    new = read_yaml_model(TaskContract, run.tasks / f"{fups[0].task_id}.yaml")
    assert new.input_artifacts[0].path == gap_artifact
    assert new.allowed_tools == ["extract_registry_run_keys"]


def test_no_followups_on_fully_planned_run(dispatched_case: DispatchedCase) -> None:
    run, _ = dispatched_case()
    critique_run(run, settings=load_settings())
    assert read_followups(run.root) == []
    assert detect_coverage_gaps(run) == []


def test_followup_generation_is_idempotent(dispatched_case: DispatchedCase) -> None:
    run, _ = dispatched_case()
    _registry_task(run).unlink()
    critique_run(run, settings=load_settings())
    first = len(read_followups(run.root))
    critique_run(run, settings=load_settings())  # gap now covered by the follow-up task
    assert len(read_followups(run.root)) == first
    assert detect_coverage_gaps(run) == []


def test_decide_follow_up_on_coverage_gap() -> None:
    assert decide("accepted", attempt=1, max_attempts=2, coverage_gap=True).action == "follow_up"
    assert (
        decide("accepted", attempt=1, max_attempts=2, needs_corroboration=True).action
        == "follow_up"
    )
    # without a gap, an accepted verdict is simply done
    assert decide("accepted", attempt=1, max_attempts=2).action == "done"
    # a hard stop still wins over a gap
    assert (
        decide(
            "accepted", attempt=1, max_attempts=2, coverage_gap=True, evidence_mismatch=True
        ).action
        == "human_review"
    )


def test_corroboration_gap_recorded(dispatched_case: DispatchedCase) -> None:
    run, _ = dispatched_case()
    real = __import__("siftmesh_core.ledgers.claim_ledger", fromlist=["read_claims"]).read_claims(
        run.root
    )[0]
    high_risk = Claim.model_validate(
        {
            "claim_id": "TASK-960-1",
            "task_id": "TASK-960",
            "status": "confirmed",
            "claim": "this host shows confirmed compromise",
            "confidence": 0.9,
            "evidence_type": real.evidence_type,
            "source_artifact": real.source_artifact,
            "source_sha256": real.source_sha256,
            "tool_name": real.tool_name,
            "tool_call_id": real.tool_call_id,
            "supporting_evidence_refs": [real.tool_call_id],
        }
    )
    tr = TaskResult(
        task_id="TASK-960",
        profile="claude_headless",
        adapter="claude_headless",
        attempt=1,
        status="success",
        tool_call_ids=[],
        claims=[high_risk],
        started_utc=_NOW,
        ended_utc=_NOW,
    )
    run.result_path("TASK-960").write_text(tr.model_dump_json(indent=2), encoding="utf-8")
    critique_run(run, settings=load_settings())
    assert any(
        f.reason == "corroboration_gap" and f.origin_claim_id == "TASK-960-1"
        for f in read_followups(run.root)
    )


def test_critique_no_followups_flag(dispatched_case: DispatchedCase, cli_app: typer.Typer) -> None:
    run, _ = dispatched_case()
    _registry_task(run).unlink()
    result = CliRunner().invoke(cli_app, ["critique", str(run.root), "--no-followups"])
    assert result.exit_code == 0, result.output
    assert read_followups(run.root) == []  # generation disabled
