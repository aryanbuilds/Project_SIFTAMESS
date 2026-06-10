"""The objective threads into the case brief, context pack, contracts, and the agent prompt."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from siftmesh_core.adapters.prompt_builder import build_task_prompt
from siftmesh_core.config import load_settings
from siftmesh_core.evidence.vault import init_case
from siftmesh_core.orchestrator.planner import generate_plan
from siftmesh_core.schemas.task import TaskContract
from siftmesh_core.schemas.yaml_io import read_yaml_model

BRIEF_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "brief"


def _planned_run_with_brief(tmp_path: Path, build_evidence: Callable[..., None]):
    evidence = tmp_path / "evidence"
    build_evidence(evidence)
    brief = tmp_path / "objective.md"
    brief.write_bytes((BRIEF_FIXTURES / "objective.md").read_bytes())
    run = init_case(tmp_path / "case", evidence, brief_path=brief)
    generate_plan(run, settings=load_settings())
    return run


def test_objective_in_case_brief_and_context_pack(
    tmp_path: Path, build_evidence: Callable[..., None]
) -> None:
    run = _planned_run_with_brief(tmp_path, build_evidence)
    brief_md = run.case_brief.read_text(encoding="utf-8")
    pack_md = run.context_pack.read_text(encoding="utf-8")
    assert "Operator incident objective" in brief_md
    assert "ROCBA" in brief_md
    assert "Incident objective (TRUSTED operator context)" in pack_md
    assert "ROCBA" in pack_md


def test_contract_context_packet_includes_brief(
    tmp_path: Path, build_evidence: Callable[..., None]
) -> None:
    run = _planned_run_with_brief(tmp_path, build_evidence)
    contracts = sorted(run.tasks.glob("TASK-*.yaml"))
    assert contracts, "planner produced no tasks"
    for path in contracts:
        contract = read_yaml_model(TaskContract, path)
        assert "context/incident_brief.md" in contract.context_packet


def test_no_brief_no_objective_in_context(
    tmp_path: Path, build_evidence: Callable[..., None]
) -> None:
    evidence = tmp_path / "evidence"
    build_evidence(evidence)
    run = init_case(tmp_path / "case", evidence)
    generate_plan(run, settings=load_settings())
    assert "Operator incident objective" not in run.case_brief.read_text(encoding="utf-8")
    assert "Incident objective (TRUSTED" not in run.context_pack.read_text(encoding="utf-8")
    for path in run.tasks.glob("TASK-*.yaml"):
        contract = read_yaml_model(TaskContract, path)
        assert "context/incident_brief.md" not in contract.context_packet


def test_prompt_objective_is_separate_from_hostile_evidence(
    tmp_path: Path, build_evidence: Callable[..., None]
) -> None:
    run = _planned_run_with_brief(tmp_path, build_evidence)
    contract = read_yaml_model(TaskContract, sorted(run.tasks.glob("TASK-*.yaml"))[0])
    marker = "OBJECTIVE_MARKER_ROCBA_FIND_INITIAL_ACCESS"
    prompt = build_task_prompt(contract, run_id=run.run_id, incident_objective=marker)

    assert "## Incident objective (TRUSTED operator context)" in prompt
    assert marker in prompt
    # The TRUSTED objective must sit OUTSIDE the spotlighted hostile-evidence delimiters.
    start = prompt.index("_EVIDENCE_START")
    end = prompt.index("_EVIDENCE_END")
    obj_at = prompt.index(marker)
    assert obj_at < start  # objective comes before the evidence block
    assert not (start < obj_at < end)  # and is never inside it


def test_prompt_without_objective_has_no_section(
    tmp_path: Path, build_evidence: Callable[..., None]
) -> None:
    run = _planned_run_with_brief(tmp_path, build_evidence)
    contract = read_yaml_model(TaskContract, sorted(run.tasks.glob("TASK-*.yaml"))[0])
    prompt = build_task_prompt(contract, run_id=run.run_id)
    assert "Incident objective (TRUSTED operator context)" not in prompt
