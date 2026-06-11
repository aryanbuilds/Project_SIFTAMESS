"""The `evidence` command group + deprecated hidden top-level aliases (zero breakage)."""

from __future__ import annotations

from siftmesh_core.cli import app
from typer.testing import CliRunner

runner = CliRunner()

_SUBS = ["extract", "memory", "decompress", "ingest"]
_ALIASES = ["extract-artifacts", "analyze-memory", "decompress", "ingest-derived"]


def test_evidence_group_help_lists_subcommands() -> None:
    result = runner.invoke(app, ["evidence", "--help"])
    assert result.exit_code == 0
    for sub in _SUBS:
        assert sub in result.output


def test_evidence_subcommands_have_help() -> None:
    for sub in _SUBS:
        result = runner.invoke(app, ["evidence", sub, "--help"])
        assert result.exit_code == 0, f"evidence {sub} --help failed"


def test_deprecated_aliases_still_work_but_hidden() -> None:
    main_help = runner.invoke(app, ["--help"])
    assert main_help.exit_code == 0
    for alias in _ALIASES:
        # still invokable (back-compat for scripts / the RUNBOOK)
        assert runner.invoke(app, [alias, "--help"]).exit_code == 0, f"{alias} alias broke"
    # but hidden from the top-level help (the canonical path is `evidence …`)
    assert "extract-artifacts" not in main_help.output
    assert "analyze-memory" not in main_help.output
    assert "ingest-derived" not in main_help.output
    # the group itself IS listed
    assert "evidence" in main_help.output
