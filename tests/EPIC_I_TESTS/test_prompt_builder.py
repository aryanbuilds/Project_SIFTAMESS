"""I3 — the task-prompt builder spotlights evidence and never dumps raw bytes."""

from __future__ import annotations

from siftmesh_core.adapters.prompt_builder import build_task_prompt
from siftmesh_core.schemas.task import InputArtifact, SafetyPolicy, TaskContract

_SHA = "a" * 64


def _contract() -> TaskContract:
    return TaskContract(
        task_id="TASK-001",
        role="evtx_security_executor",
        objective="Parse the Windows Security event log.",
        assigned_agent_profile="claude_headless",
        allowed_tools=["parse_evtx_security"],
        input_artifacts=[InputArtifact(path="Security.evtx", sha256=_SHA)],
        success_criteria=["Every claim MUST cite tool_call_id + source_sha256."],
        safety_policy=SafetyPolicy(),
    )


def test_prompt_builder_spotlights_evidence() -> None:
    prompt = build_task_prompt(_contract(), run_id="RUN-X")
    # contract content rendered
    assert "parse_evtx_security" in prompt  # the allowed tool
    assert "Every claim MUST cite" in prompt  # the success criterion
    assert "Security.evtx" in prompt and _SHA in prompt  # the artifact row (path + sha)
    # spotlighting: the evidence is fenced by the per-run datamark delimiters
    assert "EVIDENCE_START" in prompt and "EVIDENCE_END" in prompt


def test_prompt_builder_result_file_only_when_asked() -> None:
    live = build_task_prompt(_contract(), run_id="RUN-X")  # stdout agent
    filed = build_task_prompt(
        _contract(), run_id="RUN-X", result_file="results/TASK-001.agent.json"
    )
    assert "Write a TaskResult JSON" not in live
    assert "results/TASK-001.agent.json" in filed
