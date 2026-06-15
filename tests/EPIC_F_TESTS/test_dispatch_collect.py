"""F4/F5/F6 - dispatch + collect CLI/service + agent_calls audit."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
import typer
from siftmesh_core.config import load_settings
from siftmesh_core.ledgers.agent_calls import read_agent_calls
from siftmesh_core.orchestrator.scheduler import PolicyError, collect_run, dispatch_run
from siftmesh_core.run_dir import RunPaths
from typer.testing import CliRunner

RealCase = Callable[..., tuple[RunPaths, Path]]


def test_dispatch_writes_results(real_case: RealCase) -> None:
    run, _ = real_case()
    refs = dispatch_run(run, settings=load_settings())
    assert refs
    for ref in refs:
        assert run.result_path(ref.task_id).is_file()


def test_dispatch_single_task(real_case: RealCase) -> None:
    run, _ = real_case()
    refs = dispatch_run(run, settings=load_settings(), task_id="TASK-001")
    assert len(refs) == 1 and refs[0].task_id == "TASK-001"


def test_dispatch_recovers_evidence_root(real_case: RealCase) -> None:
    # No --evidence override: must be recovered from readonly_mounts.json and succeed.
    run, _ = real_case()
    refs = dispatch_run(run, settings=load_settings())
    assert all(r.status in ("success", "retry_required") for r in refs)


def test_dispatch_review_only_refused(real_case: RealCase) -> None:
    run, _ = real_case(review_only=True)
    with pytest.raises(PolicyError):
        dispatch_run(run, settings=load_settings())


def test_collect_validates_and_flags_missing(real_case: RealCase) -> None:
    run, _ = real_case()
    dispatch_run(run, settings=load_settings())
    # delete one result → collect flags it missing, does not crash
    first = sorted(run.results.glob("TASK-*.result.json"))[0]
    tid = first.name.removesuffix(".result.json")
    first.unlink()
    report = collect_run(run)
    assert tid in report.missing
    assert all(r.status == "success" for r in report.rows if r.task_id != tid)


def test_collect_flags_malformed(real_case: RealCase) -> None:
    run, _ = real_case()
    dispatch_run(run, settings=load_settings())
    target = sorted(run.results.glob("TASK-*.result.json"))[0]
    target.write_text("{not json", encoding="utf-8")
    report = collect_run(run)
    assert report.malformed


def test_agent_calls_one_line_per_dispatch(real_case: RealCase) -> None:
    run, _ = real_case()
    refs = dispatch_run(run, settings=load_settings())
    calls = read_agent_calls(run.root)
    assert len(calls) == len(refs)
    assert all(c.backend == "real" for c in calls)


def test_dispatch_cli_exit_zero(real_case: RealCase) -> None:
    from siftmesh_core.cli import app

    run, _ = real_case()
    result = CliRunner().invoke(app, ["dispatch", str(run.root), "--task", "TASK-001"])
    assert result.exit_code == 0, result.output
    assert "dispatch complete" in result.output


def test_dispatch_cli_nonexistent_run_dir(tmp_path: Path) -> None:
    from siftmesh_core.cli import app

    result = CliRunner().invoke(app, ["dispatch", str(tmp_path / "nope")])
    assert result.exit_code == 1
    assert "dispatch failed" in result.output


def test_collect_cli_exit_zero(real_case: RealCase, cli_app: typer.Typer) -> None:
    run, _ = real_case()
    dispatch_run(run, settings=load_settings())
    result = CliRunner().invoke(cli_app, ["collect", str(run.root)])
    assert result.exit_code == 0, result.output
