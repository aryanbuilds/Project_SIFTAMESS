"""The canonical triage workflow YAML validates against the Workflow schema (E4/E7)."""

from __future__ import annotations

from pathlib import Path

from siftmesh_core.schemas.workflow import Workflow
from siftmesh_core.schemas.yaml_io import read_yaml_model

_WORKFLOW = Path(__file__).resolve().parents[2] / "workflows" / "windows_initial_triage.yaml"


def test_windows_initial_triage_workflow_is_valid() -> None:
    assert _WORKFLOW.is_file(), f"missing canonical workflow at {_WORKFLOW}"
    wf = read_yaml_model(Workflow, _WORKFLOW)
    assert wf.workflow_id == "windows_initial_triage"
    assert wf.mode == "guided"
    # safety posture is fixed-True by the schema; stage order is the triage spine
    assert wf.safety.evidence_mode == "read_only"
    assert wf.steps[0] == "init_case"
    assert "plan" in wf.steps and "critique" in wf.steps and wf.steps[-1] == "report"
    assert set(wf.approval_gates) == {"plan", "dispatch", "retry", "report"}
