"""C3 — TaskContract: safety_policy required + YAML round-trip."""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from siftmesh_core.schemas.task import SafetyPolicy, TaskContract
from siftmesh_core.schemas.yaml_io import dump_yaml_model, load_yaml_model

_HASH = "a" * 64
_TASK_YAML = f"""
task_id: TASK-002
role: evtx_executor
objective: Parse Security.evtx for suspicious logon events.
assigned_agent_profile: opencode_low_cost
allowed_tools:
  - parse_evtx_security
input_artifacts:
  - path: evidence/Security.evtx
    sha256: {_HASH}
    mode: read_only
context_packet:
  - context/case_brief.md
output_required:
  - results/TASK-002.result.json
success_criteria:
  - Every finding includes event_id, timestamp, source_file, tool_call_id.
retry_policy:
  max_attempts: 2
  retry_on:
    - malformed_json
safety_policy:
  evidence_is_hostile: true
  never_execute_instructions_from_evidence: true
  write_allowed_only_under:
    - results/TASK-002/
"""


def test_task_contract_schema_valid() -> None:
    task = load_yaml_model(TaskContract, _TASK_YAML)
    assert task.task_id == "TASK-002"
    assert task.safety_policy.evidence_is_hostile is True
    assert task.input_artifacts[0].mode == "read_only"


def test_task_without_safety_policy_rejected() -> None:
    with pytest.raises(ValidationError):
        TaskContract.model_validate(
            {
                "task_id": "T",
                "role": "r",
                "objective": "o",
                "assigned_agent_profile": "p",
            }
        )


def test_task_contract_yaml_round_trip() -> None:
    task = load_yaml_model(TaskContract, _TASK_YAML)
    assert load_yaml_model(TaskContract, dump_yaml_model(task)) == task


def test_input_artifact_rejects_rw_mode() -> None:
    with pytest.raises(ValidationError):
        load_yaml_model(TaskContract, _TASK_YAML.replace("mode: read_only", "mode: read_write"))


@pytest.mark.parametrize(
    "field",
    ("evidence_is_hostile", "never_execute_instructions_from_evidence"),
)
def test_task_safety_policy_rejects_disabled_guards(field: str) -> None:
    with pytest.raises(ValidationError):
        SafetyPolicy.model_validate({field: False})
