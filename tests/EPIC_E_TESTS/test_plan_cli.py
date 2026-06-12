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
    # the exact 5 context files the planner writes (synthetic_run has no init-case extras)
    for path in (
        run.context_pack,
        run.case_brief,
        run.assumptions,
        run.tool_map,
        run.investigation_plan,
    ):
        assert path.is_file(), f"missing {path}"
    # Per-family aggregation (bd 1xy6) + multi-tool-per-hive: security, powershell, prefetch, ONE
    # registry run-keys task (both NTUSER hives), parse_mft_filesystem, + recentdocs + usb +
    # shellbags over the NTUSER hives, (+timeline) = 9 tasks.
    task_files = sorted(run.tasks.glob("TASK-*.yaml"))
    assert len(task_files) == 9
    registry = [
        c
        for c in (read_yaml_model(TaskContract, p) for p in task_files)
        if c.role == "registry_hive_executor"
    ]
    assert len(registry) == 1 and len(registry[0].input_artifacts) == 2  # both hives, one task


def test_plan_cli_missing_manifest_fails(
    runner: CliRunner, cli_app: typer.Typer, tmp_path: Path
) -> None:
    run = new_run_dir(base=tmp_path / "case_runs")
    result = runner.invoke(cli_app, ["plan", str(run.root)])
    assert result.exit_code == 1
    assert "plan failed" in result.output


def test_plan_cli_nonexistent_run_dir_fails_cleanly(
    runner: CliRunner, cli_app: typer.Typer, tmp_path: Path
) -> None:
    result = runner.invoke(cli_app, ["plan", str(tmp_path / "does-not-exist")])
    assert result.exit_code == 1
    assert "run directory does not exist" in result.output


def test_plan_cli_invalid_manifest_schema_fails(
    runner: CliRunner, cli_app: typer.Typer, synthetic_run: SyntheticRun
) -> None:
    run = synthetic_run()
    run.evidence_manifest.write_text('{"case_id": "c"}', encoding="utf-8")  # valid JSON, bad schema
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


def test_timeline_only_manifest_builds_timeline_task(synthetic_run: SyntheticRun) -> None:
    # System.evtx (evtx_other) is context-only; $MFT is now actionable (parse_mft_filesystem) AND
    # timeline-capable → a parse_mft task + one timeline task (both artifacts feed the timeline).
    run = synthetic_run(["System.evtx", "$MFT"])
    res = generate_plan(run, settings=load_settings())
    contracts = [read_yaml_model(TaskContract, p) for p in res.task_files]
    roles = sorted(c.role for c in contracts)
    assert roles == ["mft_executor", "timeline_executor"]
    timeline = next(c for c in contracts if c.role == "timeline_executor")
    assert timeline.allowed_tools == ["build_timeline"]
    assert len(timeline.input_artifacts) == 2  # System.evtx + $MFT both feed the timeline
    mft = next(c for c in contracts if c.role == "mft_executor")
    assert mft.allowed_tools == ["parse_mft_filesystem"]


def test_ntuser_hive_emits_extra_tool_tasks(synthetic_run: SyntheticRun) -> None:
    # Multi-tool-per-hive: an NTUSER.DAT feeds run-keys (primary) + recentdocs + usb (extra tools).
    run = synthetic_run(["Users/alice/NTUSER.DAT"])
    res = generate_plan(run, settings=load_settings())
    contracts = [read_yaml_model(TaskContract, p) for p in res.task_files]
    tools = sorted(c.allowed_tools[0] for c in contracts)
    assert tools == [
        "extract_registry_run_keys",
        "parse_recentdocs_mru",
        "parse_shellbags",
        "parse_usb_registry",
    ]


def test_image_only_manifest_is_actionable(synthetic_run: SyntheticRun) -> None:
    run = synthetic_run(["rocba-cdrive.E01"])
    res = generate_plan(run, settings=load_settings())
    tools = {
        tool for p in res.task_files for tool in read_yaml_model(TaskContract, p).allowed_tools
    }
    assert "extract_artifacts_from_image" in tools


def test_super_timeline_is_opt_in(synthetic_run: SyntheticRun) -> None:
    base = load_settings()
    # Default (flag off): no super-timeline task is emitted (never on the cheap auto path).
    off = generate_plan(synthetic_run(["rocba-cdrive.E01"]), settings=base)
    off_tools = {t for p in off.task_files for t in read_yaml_model(TaskContract, p).allowed_tools}
    assert "build_super_timeline" not in off_tools
    # Opt-in (flag on): exactly one build_super_timeline task over the disk image.
    on = generate_plan(
        synthetic_run(["rocba-cdrive.E01"]),
        settings=base.model_copy(update={"enable_super_timeline": True}),
    )
    st = [
        c
        for p in on.task_files
        if (c := read_yaml_model(TaskContract, p)).allowed_tools == ["build_super_timeline"]
    ]
    assert len(st) == 1 and st[0].input_artifacts[0].path == "rocba-cdrive.E01"
