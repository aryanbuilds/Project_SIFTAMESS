"""G1/G5 — critique + retry CLI commands."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import typer
from siftmesh_core.cli import app
from siftmesh_core.ledgers.retries import read_retries
from siftmesh_core.run_dir import RunPaths
from siftmesh_core.schemas.claim import Claim
from siftmesh_core.schemas.task import TaskContract
from siftmesh_core.schemas.task_result import TaskResult
from siftmesh_core.schemas.yaml_io import read_yaml_model
from typer.testing import CliRunner

DispatchedCase = Callable[..., tuple[RunPaths, Path]]
_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _craft_bad_result(run: RunPaths, task_id: str) -> None:
    bad = Claim.model_validate(
        {
            "claim_id": f"{task_id}-BAD",
            "task_id": task_id,
            "status": "confirmed",
            "claim": "something happened",
            "confidence": 0.9,
            "evidence_type": "x",
            "source_artifact": "Security.evtx",
            "source_sha256": "a" * 64,
            "tool_name": "parse_evtx_security",
            "tool_call_id": "TOOL-999",
        }
    )
    tr = TaskResult(
        task_id=task_id,
        profile="claude_headless",
        adapter="claude_headless",
        attempt=1,
        status="success",
        tool_call_ids=[],
        claims=[bad],
        started_utc=_NOW,
        ended_utc=_NOW,
    )
    run.result_path(task_id).write_text(tr.model_dump_json(indent=2), encoding="utf-8")


def test_critique_cli_exit_zero(dispatched_case: DispatchedCase, cli_app: typer.Typer) -> None:
    run, _ = dispatched_case()
    result = CliRunner().invoke(cli_app, ["critique", str(run.root)])
    assert result.exit_code == 0, result.output
    assert "critique complete" in result.output


def test_critique_cli_nonexistent_run_dir(cli_app: typer.Typer, tmp_path: Path) -> None:
    result = CliRunner().invoke(cli_app, ["critique", str(tmp_path / "nope")])
    assert result.exit_code == 1
    assert "critique failed" in result.output


def test_retry_creates_tightened_contract(dispatched_case: DispatchedCase) -> None:
    run, _ = dispatched_case()
    task_id = sorted(p.stem.replace(".result", "") for p in run.results.glob("TASK-*.result.json"))[
        0
    ]
    _craft_bad_result(run, task_id)  # force a retry_required verdict
    before = read_yaml_model(TaskContract, run.tasks / f"{task_id}.yaml").success_criteria
    result = CliRunner().invoke(app, ["retry", str(run.root), task_id])
    assert result.exit_code == 0, result.output
    after = read_yaml_model(TaskContract, run.tasks / f"{task_id}.yaml").success_criteria
    assert len(after) > len(before)
    assert any("tool_call_id and source_sha256" in c for c in after)
    assert read_retries(run.root)
    # the re-dispatched floor run produced a real (anchored) result for attempt 2
    tr = TaskResult.model_validate_json(run.result_path(task_id).read_text(encoding="utf-8"))
    assert tr.attempt == 2 and tr.status == "success"


def test_retry_refused_when_decide_not_retry(dispatched_case: DispatchedCase) -> None:
    run, _ = dispatched_case()  # clean floor → accepted → decide=done → retry refused
    task_id = sorted(p.stem.replace(".result", "") for p in run.results.glob("TASK-*.result.json"))[
        0
    ]
    result = CliRunner().invoke(app, ["retry", str(run.root), task_id])
    assert result.exit_code == 1
    assert "retry refused" in result.output
