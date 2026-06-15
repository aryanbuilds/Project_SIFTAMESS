"""J3 edge cases - the real failures from live runs must render gracefully, never as facts."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from siftmesh_core.ledgers.agent_calls import append_agent_call
from siftmesh_core.ledgers.claim_ledger import append_claim
from siftmesh_core.ledgers.critic_verdicts import append_critic_verdict
from siftmesh_core.ledgers.tool_call_ledger import append_tool_result
from siftmesh_core.reports import generate_final_report, load_report_view, split_body
from siftmesh_core.reports.attack import lookup, lookup_for_claim
from siftmesh_core.reports.loader import MAX_DETAILED_FINDINGS
from siftmesh_core.run_dir import RunPaths, new_run_dir
from siftmesh_core.schemas.agent_call import AgentCall
from siftmesh_core.schemas.audit import CriticVerdict
from siftmesh_core.schemas.claim import Claim
from siftmesh_core.schemas.tool_result import ToolResult

_T = datetime(2026, 1, 1, tzinfo=UTC)


def _claim(
    cid: str, *, status: str = "confirmed", tool_call_id: str = "TOOL-001", **over: object
) -> Claim:
    base: dict[str, object] = {
        "claim_id": cid,
        "task_id": cid.split("-CLAIM")[0],
        "status": status,
        "claim": f"finding {cid}",
        "confidence": 0.9,
        "evidence_type": "windows_event_log",
        "source_artifact": "evidence/extracted/Security.evtx",
        "source_sha256": "a" * 64,
        "tool_name": "parse_evtx_security",
        "tool_call_id": tool_call_id,
        "supporting_evidence_refs": [tool_call_id],
    }
    base.update(over)
    return Claim.model_validate(base)


def _body(run: RunPaths) -> str:
    return split_body(generate_final_report(run).read_text(encoding="utf-8"))


def test_failed_tool_is_flagged(tmp_path: Path) -> None:
    run = new_run_dir(base=tmp_path / "case_runs")
    append_tool_result(
        run.root,
        ToolResult(
            tool_call_id="TOOL-009",
            tool_name="extract_artifacts_from_image",
            source_artifact="rocba-cdrive.e01",
            source_sha256="c" * 64,
            start_time_utc=_T,
            end_time_utc=_T,
            status="error",
            backend="sift_lane",
            tool_version="1",
            error_code="parse_error",
        ),
    )
    append_claim(run.root, _claim("TASK-001-CLAIM-001", tool_call_id="TOOL-009"))
    view = load_report_view(run)
    assert view.failed_tool_call_ids == frozenset({"TOOL-009"})
    assert "TASK-001-CLAIM-001" in view.claims_on_failed_tools
    body = _body(run)
    assert "tool invocation(s) failed" in body
    assert "did not fully succeed" in body  # the finding is flagged


def test_fell_back_agent_in_audit(tmp_path: Path) -> None:
    run = new_run_dir(base=tmp_path / "case_runs")
    append_agent_call(
        run.root,
        AgentCall(
            agent_call_id="AGENT-001",
            task_id="TASK-001",
            profile="claude_headless",
            adapter="deterministic_executor",
            backend="real",
            attempt=1,
            start_time_utc=_T,
            end_time_utc=_T,
            status="fell_back",
            fell_back_from="claude_headless",
        ),
    )
    append_claim(run.root, _claim("TASK-001-CLAIM-001"))
    body = _body(run)
    assert "Adapter fall-backs" in body
    assert "claude_headless" in body and "deterministic_executor" in body


def test_escalation_and_human_review_surfaced(tmp_path: Path) -> None:
    run = new_run_dir(base=tmp_path / "case_runs")
    append_claim(run.root, _claim("TASK-001-CLAIM-001"))
    append_critic_verdict(
        run.root,
        CriticVerdict(
            verdict="escalation_required",
            reasons=["a claim contradicts another"],
            affected_claim_ids=[],
            task_id="TASK-001",
            verdict_id="VERDICT-001",
            decided_utc=_T,
        ),
    )
    append_critic_verdict(
        run.root,
        CriticVerdict(
            verdict="human_review_required",
            reasons=["injection-affected"],
            affected_claim_ids=[],
            task_id="TASK-002",
            verdict_id="VERDICT-002",
            decided_utc=_T,
        ),
    )
    body = _body(run)
    assert "escalation_required" in body and "human_review_required" in body


def test_retry_only_task_in_self_correction(tmp_path: Path) -> None:
    run = new_run_dir(base=tmp_path / "case_runs")
    append_critic_verdict(
        run.root,
        CriticVerdict(
            verdict="retry_required",
            reasons=["a claim is unsupported"],
            affected_claim_ids=[],
            task_id="TASK-013",
            verdict_id="VERDICT-001",
            decided_utc=_T,
        ),
    )
    body = _body(run)
    assert "Self-correction" in body
    assert "TASK-013" in body  # surfaced as still-requiring-retry, NOT as a finding
    assert "Confirmed findings" in body and "None." in body


def test_large_run_summarized(tmp_path: Path) -> None:
    run = new_run_dir(base=tmp_path / "case_runs")
    for i in range(1, MAX_DETAILED_FINDINGS + 21):  # exceed the detail cap
        append_claim(run.root, _claim(f"TASK-{i:03d}-CLAIM-001"))
    view = load_report_view(run)
    assert len(view.confirmed) == MAX_DETAILED_FINDINGS + 20
    body = _body(run)
    assert "additional finding(s)" in body  # capped detail + bucket summary
    assert "Counts by evidence type" in body


def test_attack_map_known_and_unknown() -> None:
    assert lookup("registry_autostart").technique == "T1547"  # type: ignore[union-attr]
    assert lookup("timeline") is None  # mapped-to-null
    assert lookup("a_brand_new_unmapped_type") is None  # unknown → graceful None, no KeyError
    ps = _claim(
        "TASK-001-CLAIM-001",
        evidence_type="windows_event_log",
        claim="PowerShell EventID 4104 script-block logging observed",
    )
    assert lookup_for_claim(ps).subtechnique == "T1059.001"  # type: ignore[union-attr]  # refinement
