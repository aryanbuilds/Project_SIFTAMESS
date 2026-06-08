"""E1 (`plan` command), E8 (--review-only), and graceful degradation."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import typer
from siftmesh_core.config import load_settings
from siftmesh_core.orchestrator.planner import generate_plan
from siftmesh_core.run_dir import RunPaths, new_run_dir
from siftmesh_core.schemas.plan import InvestigationPlan
from siftmesh_core.schemas.task import TaskContract
from siftmesh_core.schemas.yaml_io import read_yaml_model
from typer.testing import CliRunner

SyntheticRun = Callable[..., RunPaths]


def test_plan_cli_exits_zero_and_writes_artifacts(
    runner: CliRunner, cli_app: typer.Typer, synthetic_run: SyntheticRun
) -> None:
    run = synthetic_run()
    result = runner.invoke(cli_app, ["plan", str(run.root)])
    assert result.exit_code == 0, result.output
    assert sum(1 for _ in run.context.glob("*")) >= 5  # 5 context files
    assert len(list(run.tasks.glob("TASK-*.yaml"))) >= 2


def test_plan_cli_missing_manifest_fails(
    runner: CliRunner, cli_app: typer.Typer, tmp_path: Path
) -> None:
    run = new_run_dir(base=tmp_path / "case_runs")
    result = runner.invoke(cli_app, ["plan", str(run.root)])
    assert result.exit_code == 1
    assert "plan failed" in result.output


def test_plan_logs_started_and_complete(synthetic_run: SyntheticRun) -> None:
    run = synthetic_run()
    generate_plan(run, settings=load_settings())
    events = run.orchestration_events.read_text(encoding="utf-8")
    assert "plan_started" in events and "plan_complete" in events


def test_review_only_flag_recorded_no_results(synthetic_run: SyntheticRun) -> None:
    run = synthetic_run()
    res = generate_plan(run, settings=load_settings(), review_only=True)
    assert res.review_only is True
    plan = read_yaml_model(InvestigationPlan, run.investigation_plan)
    assert plan.review_only is True
    assert "review-only" in run.case_brief.read_text(encoding="utf-8").lower()
    # dispatch is unbuilt in Epic E -> no results were produced
    assert not list(run.results.glob("*"))


def test_empty_manifest_degrades_gracefully(synthetic_run: SyntheticRun) -> None:
    run = synthetic_run([])
    res = generate_plan(run, settings=load_settings())
    assert len(res.task_files) == 0  # honest: no fabricated tasks
    assert run.context_pack.is_file() and run.investigation_plan.is_file()


def test_image_only_manifest_is_actionable(synthetic_run: SyntheticRun) -> None:
    run = synthetic_run(["rocba-cdrive.E01"])
    res = generate_plan(run, settings=load_settings())
    tools = {
        tool for p in res.task_files for tool in read_yaml_model(TaskContract, p).allowed_tools
    }
    assert "extract_artifacts_from_image" in tools
