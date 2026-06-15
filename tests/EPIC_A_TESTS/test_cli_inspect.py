"""Debug inspection commands (CLAUDE §4): tasks list/show, claims list/show, audit tail.

Real read-only views over a real run (the shared root factory: manifest + plan +
dispatch of the committed fixtures) - these were the last CLI print stubs. Each test
asserts genuine run-dir content.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import typer
from siftmesh_core.ledgers.claim_ledger import read_claims
from siftmesh_core.run_dir import RunPaths
from typer.testing import CliRunner

MakeRealRun = Callable[..., tuple[RunPaths, Path]]


def _dispatched_run(make_real_run: MakeRealRun) -> tuple[RunPaths, Path]:
    return make_real_run(dispatch=True)


def test_tasks_list_shows_contracts_and_status(
    runner: CliRunner, cli_app: typer.Typer, make_real_run: MakeRealRun
) -> None:
    run, _ = _dispatched_run(make_real_run)
    result = runner.invoke(cli_app, ["tasks", "list", str(run.root)])
    assert result.exit_code == 0
    assert "TASK-001" in result.output
    assert "status=" in result.output
    assert "task(s)" in result.output


def test_tasks_show_echoes_validated_contract(
    runner: CliRunner, cli_app: typer.Typer, make_real_run: MakeRealRun
) -> None:
    run, _ = _dispatched_run(make_real_run)
    result = runner.invoke(cli_app, ["tasks", "show", str(run.root), "TASK-001"])
    assert result.exit_code == 0
    assert "task_id: TASK-001" in result.output
    assert "safety_policy" in result.output


def test_tasks_show_unknown_task_exits_1(
    runner: CliRunner, cli_app: typer.Typer, make_real_run: MakeRealRun
) -> None:
    run, _ = _dispatched_run(make_real_run)
    result = runner.invoke(cli_app, ["tasks", "show", str(run.root), "TASK-999"])
    assert result.exit_code == 1


def test_claims_list_shows_ledger_and_unsupported_count(
    runner: CliRunner, cli_app: typer.Typer, make_real_run: MakeRealRun
) -> None:
    run, _ = _dispatched_run(make_real_run)
    result = runner.invoke(cli_app, ["claims", "list", str(run.root)])
    assert result.exit_code == 0
    assert "claim(s) in the findings ledger" in result.output
    assert "unsupported" in result.output


def test_claims_show_prints_full_claim_json(
    runner: CliRunner, cli_app: typer.Typer, make_real_run: MakeRealRun
) -> None:
    run, _ = _dispatched_run(make_real_run)
    claims = read_claims(run.root)
    assert claims, "precondition: the dispatched run promoted at least one claim"
    cid = claims[0].claim_id
    result = runner.invoke(cli_app, ["claims", "show", str(run.root), cid])
    assert result.exit_code == 0
    assert cid in result.output
    assert "source_sha256" in result.output


def test_claims_show_unknown_claim_exits_1(
    runner: CliRunner, cli_app: typer.Typer, make_real_run: MakeRealRun
) -> None:
    run, _ = _dispatched_run(make_real_run)
    result = runner.invoke(cli_app, ["claims", "show", str(run.root), "CLAIM-NOPE"])
    assert result.exit_code == 1


def test_audit_tail_events_and_tool_calls(
    runner: CliRunner, cli_app: typer.Typer, make_real_run: MakeRealRun
) -> None:
    run, _ = _dispatched_run(make_real_run)
    events = runner.invoke(cli_app, ["audit", "tail", str(run.root)])
    assert events.exit_code == 0
    assert "events line(s)" in events.output
    tools = runner.invoke(cli_app, ["audit", "tail", str(run.root), "--ledger", "tool-calls"])
    assert tools.exit_code == 0
    assert "tool_call_id" in tools.output  # raw JSONL provenance lines


def test_audit_tail_unknown_ledger_exits_1(
    runner: CliRunner, cli_app: typer.Typer, make_real_run: MakeRealRun
) -> None:
    run, _ = _dispatched_run(make_real_run)
    result = runner.invoke(cli_app, ["audit", "tail", str(run.root), "--ledger", "bogus"])
    assert result.exit_code == 1


def test_inspection_commands_reject_missing_run_dir(
    runner: CliRunner, cli_app: typer.Typer, tmp_path: Path
) -> None:
    missing = str(tmp_path / "nope")
    for args in (
        ["tasks", "list", missing],
        ["claims", "list", missing],
        ["audit", "tail", missing],
    ):
        result = runner.invoke(cli_app, args)
        assert result.exit_code == 1, args
