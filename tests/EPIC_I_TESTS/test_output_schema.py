"""I4 - executor output-schema enforcement: a malformed result drives the retry loop."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from siftmesh_core.adapters.base import AdapterContext
from siftmesh_core.adapters.generic_shell_adapter import GenericShellAdapter
from siftmesh_core.config import load_settings
from siftmesh_core.orchestrator.scheduler import collect_run
from siftmesh_core.run_dir import new_run_dir
from siftmesh_core.schemas.task import InputArtifact, SafetyPolicy, TaskContract
from siftmesh_core.schemas.yaml_io import dump_yaml_model


def _contract() -> TaskContract:
    return TaskContract(
        task_id="TASK-001",
        role="evtx_security_executor",
        objective="Parse the Security log.",
        assigned_agent_profile="generic_shell",
        allowed_tools=["parse_evtx_security"],
        input_artifacts=[InputArtifact(path="Security.evtx", sha256="a" * 64)],
        success_criteria=["cite tool_call_id"],
        safety_policy=SafetyPolicy(),
    )


def test_collect_rejects_bad_schema(tmp_path: Path) -> None:
    run = new_run_dir(base=tmp_path / "case_runs")
    (run.tasks / "TASK-001.yaml").write_text(dump_yaml_model(_contract()), encoding="utf-8")
    run.result_path("TASK-001").write_text("{ not valid json", encoding="utf-8")  # malformed
    report = collect_run(run)
    assert "TASK-001" in report.malformed


def test_generic_shell_malformed_result_is_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = load_settings(generic_agent_cmd="/usr/bin/true")  # available() via which()
    run = new_run_dir(base=tmp_path / "case_runs")

    def _fake_run(argv: list[str], **_: object) -> SimpleNamespace:
        Path(argv[2]).write_text("{ not a TaskResult ", encoding="utf-8")  # agent emits garbage
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("siftmesh_core.adapters.generic_shell_adapter.subprocess.run", _fake_run)
    adapter = GenericShellAdapter(settings=settings)
    ctx = AdapterContext(run=run, evidence_root=tmp_path, settings=settings)
    result = adapter._execute(_contract(), ctx)
    assert result.status == "retry_required"  # I4: schema-invalid → retry (feeds DECIDE/G)
    assert result.retry_cause == "malformed_result"
