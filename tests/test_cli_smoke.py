"""A2 acceptance: `siftmesh --help` lists every registered command, exit 0."""

from __future__ import annotations

import pytest
import typer
from siftmesh_core.protocol_sift import PROTOCOL_SIFT_SKILLS
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
]

COMMAND_SMOKE_CASES = [
    # init-case is no longer a stub (real behaviour lands in Epic B) — see
    # tests/test_init_case_integration.py.
    (("plan", "RUN-001"), "plan RUN-001"),
    (("dispatch", "RUN-001"), "dispatch RUN-001"),
    (("collect", "RUN-001"), "collect RUN-001"),
    (("critique", "RUN-001"), "critique RUN-001"),
    (("report", "RUN-001"), "report RUN-001"),
    (("replay", "RUN-001"), "replay RUN-001"),
    (("run", "case01", "--evidence", "evidence"), "run case01"),
    (("resume", "RUN-001"), "resume RUN-001"),
    (("status", "RUN-001"), "status RUN-001"),
    (("retry", "TASK-001"), "retry TASK-001"),
    (("approve", "RUN-001", "--gate", "plan"), "approve RUN-001"),
    (("reject", "RUN-001", "--gate", "retry"), "reject RUN-001"),
    (("tasks", "list", "RUN-001"), "tasks list RUN-001"),
    (("tasks", "show", "RUN-001", "TASK-001"), "tasks show RUN-001 TASK-001"),
    (("claims", "list", "RUN-001"), "claims list RUN-001"),
    (("claims", "show", "CLAIM-001"), "claims show CLAIM-001"),
    (("audit", "tail", "RUN-001"), "audit tail RUN-001"),
]


def test_help_exit_zero(runner: CliRunner, cli_app: typer.Typer) -> None:
    result = runner.invoke(cli_app, ["--help"])
    assert result.exit_code == 0


@pytest.mark.parametrize("command", EXPECTED_COMMANDS)
def test_help_lists_command(runner: CliRunner, cli_app: typer.Typer, command: str) -> None:
    result = runner.invoke(cli_app, ["--help"])
    assert result.exit_code == 0
    assert command in result.output


def test_version_exit_zero(runner: CliRunner, cli_app: typer.Typer) -> None:
    result = runner.invoke(cli_app, ["--version"])
    assert result.exit_code == 0
    assert "siftmesh 0.1.0" in result.output


@pytest.mark.parametrize(("args", "expected"), COMMAND_SMOKE_CASES)
def test_registered_stub_commands_execute(
    runner: CliRunner,
    cli_app: typer.Typer,
    args: tuple[str, ...],
    expected: str,
) -> None:
    result = runner.invoke(cli_app, list(args))
    assert result.exit_code == 0
    assert expected in result.output


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
