"""A2 acceptance: `siftmesh --help` lists every registered command, exit 0."""

from __future__ import annotations

import types
from pathlib import Path

import pytest
import typer
from siftmesh_core.protocol_sift import PROTOCOL_SIFT_SKILLS
from siftmesh_core.run_dir import new_run_dir
from typer.testing import CliRunner

EXPECTED_COMMANDS = [
    "init-case",
    "plan",
    "dispatch",
    "collect",
    "critique",
    "report",
    "replay",
    "run",
    "resume",
    "status",
    "doctor",
    "retry",
    "approve",
    "reject",
    "tasks",
    "claims",
    "audit",
    "protocol-sift",
    "evidence",  # the forensic specialists now live under `siftmesh evidence …` (extract/memory/…)
    "mcp-serve",
]

# Forensic specialists are grouped under `siftmesh evidence` (old top-level names kept as hidden
# deprecated aliases - see test_evidence_group.py).
EVIDENCE_SUBCOMMANDS = ["extract", "memory", "decompress", "ingest"]

# No print stubs remain: every registered command has real behaviour covered by its
# per-epic test folder (the debug inspection commands are tested in test_cli_inspect.py).


def test_help_exit_zero(runner: CliRunner, cli_app: typer.Typer) -> None:
    result = runner.invoke(cli_app, ["--help"])
    assert result.exit_code == 0


@pytest.mark.parametrize("command", EXPECTED_COMMANDS)
def test_help_lists_command(runner: CliRunner, cli_app: typer.Typer, command: str) -> None:
    result = runner.invoke(cli_app, ["--help"])
    assert result.exit_code == 0
    assert command in result.output


@pytest.mark.parametrize("sub", EVIDENCE_SUBCOMMANDS)
def test_evidence_group_subcommands(runner: CliRunner, cli_app: typer.Typer, sub: str) -> None:
    result = runner.invoke(cli_app, ["evidence", "--help"])
    assert result.exit_code == 0
    assert sub in result.output


def test_version_exit_zero(runner: CliRunner, cli_app: typer.Typer) -> None:
    result = runner.invoke(cli_app, ["--version"])
    assert result.exit_code == 0
    assert "siftmesh 0.1.0" in result.output


def test_protocol_sift_inspect_outputs_status(runner: CliRunner, cli_app: typer.Typer) -> None:
    result = runner.invoke(cli_app, ["protocol-sift", "inspect"])
    assert result.exit_code == 0
    assert "Protocol SIFT installed" in result.output
    assert "Claude Code installed" in result.output


def test_protocol_sift_skills_list_outputs_registered_skills(
    runner: CliRunner, cli_app: typer.Typer
) -> None:
    result = runner.invoke(cli_app, ["protocol-sift", "skills", "list"])
    assert result.exit_code == 0
    for skill in PROTOCOL_SIFT_SKILLS:
        assert skill in result.output


def test_protocol_sift_inspect_writes_capability_map(
    runner: CliRunner, cli_app: typer.Typer, tmp_path: Path
) -> None:
    run = new_run_dir(base=tmp_path / "case_runs")
    result = runner.invoke(cli_app, ["protocol-sift", "inspect", "--run-dir", str(run.root)])
    assert result.exit_code == 0
    assert "capability map written" in result.output
    assert run.protocol_sift_capabilities.is_file()


def test_extract_artifacts_cli_wired(
    runner: CliRunner, cli_app: typer.Typer, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = types.SimpleNamespace(
        status="success",
        extracted_count=3,
        failed_count=1,
        tool_call_id="TOOL-001",
        partition_offset=0,
    )
    monkeypatch.setattr(
        "siftmesh_core.mcp_gateway.tools.image_tools.extract_artifacts_from_image",
        lambda *a, **k: fake,
    )
    result = runner.invoke(
        cli_app,
        [
            "extract-artifacts",
            str(tmp_path / "run"),
            "--evidence",
            str(tmp_path),
            "--image",
            "x.e01",
        ],
    )
    assert result.exit_code == 0
    assert "extract-artifacts: status=success extracted=3 failed=1" in result.output


def test_analyze_memory_cli_fails_closed_message(
    runner: CliRunner, cli_app: typer.Typer, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from siftmesh_core.mcp_gateway.backends import BackendUnavailableError

    def boom(*a: object, **k: object) -> object:
        raise BackendUnavailableError("vol not found")

    monkeypatch.setattr("siftmesh_core.mcp_gateway.tools.memory_tools.analyze_memory", boom)
    result = runner.invoke(
        cli_app,
        ["analyze-memory", str(tmp_path / "run"), "--evidence", str(tmp_path), "--memory", "m.raw"],
    )
    assert result.exit_code == 1
    assert "analyze-memory failed" in result.output
