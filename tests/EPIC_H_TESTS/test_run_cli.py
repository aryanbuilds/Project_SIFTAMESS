"""H6/H7 - the `run`/`resume`/`status`/`approve`/`reject` CLI over the real engine."""

from __future__ import annotations

from pathlib import Path

import typer
from typer.testing import CliRunner


def _case(tmp_path: Path) -> str:
    return str(tmp_path / "case")


def _run_root(tmp_path: Path) -> Path:
    return next((tmp_path / "case" / "case_runs").glob("RUN-*"))


def test_run_auto_cli_completes(
    runner: CliRunner, cli_app: typer.Typer, tmp_path: Path, evidence_dir: Path
) -> None:
    result = runner.invoke(
        cli_app, ["run", _case(tmp_path), "--evidence", str(evidence_dir), "--auto"]
    )
    assert result.exit_code == 0, result.output
    assert "status : complete" in result.output
    assert list(_run_root(tmp_path).glob("run_state.json"))


def test_run_review_only_cli_no_dispatch(
    runner: CliRunner, cli_app: typer.Typer, tmp_path: Path, evidence_dir: Path
) -> None:
    result = runner.invoke(
        cli_app, ["run", _case(tmp_path), "--evidence", str(evidence_dir), "--review-only"]
    )
    assert result.exit_code == 0, result.output
    run_root = _run_root(tmp_path)
    assert not list((run_root / "results").glob("TASK-*.result.json"))


def test_run_guided_then_approve_and_status_cli(
    runner: CliRunner, cli_app: typer.Typer, tmp_path: Path, evidence_dir: Path
) -> None:
    started = runner.invoke(
        cli_app, ["run", _case(tmp_path), "--evidence", str(evidence_dir), "--auto-human-loop"]
    )
    assert started.exit_code == 0, started.output
    assert "awaiting approval" in started.output and "--gate plan" in started.output
    run_root = _run_root(tmp_path)

    approved = runner.invoke(cli_app, ["approve", str(run_root), "--gate", "plan"])
    assert approved.exit_code == 0, approved.output
    assert "approved gate plan" in approved.output

    status = runner.invoke(cli_app, ["status", str(run_root)])
    assert status.exit_code == 0, status.output
    assert "state" in status.output and "mode" in status.output


def test_approve_unknown_gate_fails(
    runner: CliRunner, cli_app: typer.Typer, tmp_path: Path, evidence_dir: Path
) -> None:
    runner.invoke(
        cli_app, ["run", _case(tmp_path), "--evidence", str(evidence_dir), "--review-only"]
    )
    run_root = _run_root(tmp_path)
    result = runner.invoke(cli_app, ["approve", str(run_root), "--gate", "bogus"])
    assert result.exit_code == 1
    assert "unknown gate" in result.output
