"""C1/C4/C5 — provenance, tool/critic/run, agent/workflow schemas."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from siftmesh_core.schemas import (
    AgentProfile,
    CriticVerdict,
    RunState,
    ToolCall,
    ToolResult,
    Workflow,
    export_json_schemas,
)
from siftmesh_core.schemas.yaml_io import load_yaml_model

_HASH = "b" * 64


def _tool_result(**over: object) -> ToolResult:
    base: dict[str, object] = {
        "tool_call_id": "TOOL-001",
        "tool_name": "parse_evtx_security",
        "source_artifact": "evidence/Security.evtx",
        "source_sha256": _HASH,
        "start_time_utc": datetime(2026, 1, 1, tzinfo=UTC),
        "end_time_utc": datetime(2026, 1, 1, 0, 0, 1, tzinfo=UTC),
        "status": "success",
        "backend": "evtx",
        "tool_version": "0.1.0",
    }
    base.update(over)
    return ToolResult.model_validate(base)


def test_tool_result_valid_and_utc_z() -> None:
    data = json.loads(_tool_result().model_dump_json())
    assert data["start_time_utc"].endswith("Z")
    assert data["error_code"] is None


def test_tool_result_requires_provenance() -> None:
    with pytest.raises(ValidationError):
        ToolResult.model_validate({"tool_call_id": "x", "status": "success"})


def test_tool_result_rejects_bad_status() -> None:
    with pytest.raises(ValidationError):
        _tool_result(status="kinda-worked")


def test_tool_call_and_critic_verdict() -> None:
    call = ToolCall(
        tool_call_id="TOOL-001",
        tool_name="parse_evtx_security",
        args={"channel": "Security"},
        requested_utc=datetime(2026, 1, 1, tzinfo=UTC),
    )
    assert call.args["channel"] == "Security"
    verdict = CriticVerdict(verdict="retry_required", reasons=["missing tool_call_id"])
    assert verdict.affected_claim_ids == []
    with pytest.raises(ValidationError):
        CriticVerdict(verdict="looks-fine")


def test_run_state_resumable_round_trip() -> None:
    state = RunState(run_id="RUN-1", state="critique", iteration=2, gates={"plan": "approved"})
    assert RunState.model_validate_json(state.model_dump_json()) == state
    with pytest.raises(ValidationError):
        RunState(run_id="r", state="not-a-state")
    with pytest.raises(ValidationError):
        RunState(run_id="r", gates={"plan": "maybe"})


def test_agent_profile_enums() -> None:
    profile = AgentProfile(
        profile_id="p1", kind="claude_code", model_tier="high", cost_class="expensive"
    )
    assert profile.model_tier == "high"
    with pytest.raises(ValidationError):
        AgentProfile(profile_id="p", kind="k", model_tier="ultra", cost_class="cheap")


_WORKFLOW_YAML = """
workflow_id: windows_initial_triage
mode: auto
limits:
  max_iterations: 3
  max_agent_tasks: 10
approval_gates:
  - plan
  - report
agents:
  - opencode_low_cost
retry_policy:
  max_attempts: 2
steps:
  - init_case
  - plan
  - dispatch
  - collect
  - critique
  - report
"""


def test_workflow_yaml_parses() -> None:
    wf = load_yaml_model(Workflow, _WORKFLOW_YAML)
    assert wf.mode == "auto"
    assert wf.limits.max_iterations == 3
    assert wf.safety.raw_shell is False
    assert wf.safety.treat_evidence_as_hostile is True
    assert wf.safety.restrict_writes_to_run_directory is True
    assert "plan" in wf.approval_gates


def test_workflow_rejects_raw_shell_true() -> None:
    with pytest.raises(ValidationError):
        Workflow.model_validate({"workflow_id": "w", "mode": "auto", "safety": {"raw_shell": True}})


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("allow_destructive_tools", True),
        ("treat_evidence_as_hostile", False),
        ("restrict_writes_to_run_directory", False),
    ),
)
def test_workflow_rejects_disabled_safety_flags(field: str, value: bool) -> None:
    with pytest.raises(ValidationError):
        Workflow.model_validate({"workflow_id": "w", "mode": "auto", "safety": {field: value}})


def test_workflow_rejects_bad_mode_and_limits() -> None:
    with pytest.raises(ValidationError):
        Workflow.model_validate({"workflow_id": "w", "mode": "yolo"})
    with pytest.raises(ValidationError):
        Workflow.model_validate(
            {"workflow_id": "w", "mode": "auto", "limits": {"max_iterations": 0}}
        )


def test_json_schema_export_covers_core_models() -> None:
    schemas = export_json_schemas()
    for name in ("Claim", "TaskContract", "ToolResult"):
        assert schemas[name]["type"] == "object"
    assert schemas["ToolResult"]["additionalProperties"] is False


def test_schema_models_validate_assignment() -> None:
    result = _tool_result()
    with pytest.raises(ValidationError):
        result.source_sha256 = "not-a-sha256"
