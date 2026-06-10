"""L5e — bypass test: critic boundary (threat T6 · OWASP LLM09 · ASI-T7).

Asserts the EFFECT: a claim with no real tool-call anchor is REJECTED by the deterministic
critic (retry_required) and NEVER promoted to the claim ledger; and an unsupported claim surfaces in
the report ONLY in the rejected appendix (Appendix B), never as a fact in the findings — the
"checker-out-of-the-loop cannot pass" guarantee. Satisfies CLAUDE §14.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from siftmesh_core.config import load_settings
from siftmesh_core.ledgers.claim_ledger import read_claims
from siftmesh_core.orchestrator.critic import critique_run
from siftmesh_core.reports.final_report import generate_final_report
from siftmesh_core.reports.loader import load_report_view
from siftmesh_core.run_dir import RunPaths
from siftmesh_core.schemas.claim import Claim
from siftmesh_core.schemas.task_result import TaskResult

DispatchedCase = Callable[..., tuple[RunPaths, Path]]
_NOW = datetime(2026, 1, 1, tzinfo=UTC)
_MARKER = "ZZZ-UNSUPPORTED-FABRICATION-MARKER"


def _write_result(run: RunPaths, task_id: str, claims: list[Claim]) -> None:
    tr = TaskResult(
        task_id=task_id,
        profile="claude_headless",
        adapter="claude_headless",
        attempt=1,
        status="success",
        tool_call_ids=[],
        claims=claims,
        started_utc=_NOW,
        ended_utc=_NOW,
    )
    run.result_path(task_id).write_text(tr.model_dump_json(indent=2), encoding="utf-8")


def test_unanchored_claim_rejected_not_promoted(dispatched_case: DispatchedCase) -> None:
    # The Claim schema ITSELF refuses a 'confirmed' claim with no anchor (defense layer 1), so an
    # under-anchored agent claim lands as 'unsupported' — which the critic then rejects (layer 2)
    # and never promotes to a fact. This asserts layer 2 (the realistic agent output).
    run, _ = dispatched_case()
    promoted_before = {c.claim_id for c in read_claims(run.root)}
    unanchored = Claim.model_validate(
        {
            "claim_id": "TASK-930-1",
            "task_id": "TASK-930",
            "status": "unsupported",  # no anchor is only valid for 'unsupported'
            "claim": "Attacker established persistence (no tool evidence)",
            "confidence": 0.95,
            "evidence_type": "registry_autostart",
            "source_artifact": None,
            "source_sha256": None,
            "tool_name": None,
            "tool_call_id": None,
        }
    )
    _write_result(run, "TASK-930", [unanchored])
    verdicts = {v.task_id: v for v in critique_run(run, settings=load_settings())}
    assert verdicts["TASK-930"].verdict == "retry_required"
    assert "TASK-930-1" in verdicts["TASK-930"].affected_claim_ids
    promoted_after = {c.claim_id for c in read_claims(run.root)}
    assert "TASK-930-1" not in promoted_after
    assert promoted_after == promoted_before  # the unsupported claim was never promoted to a fact


def test_confirmed_claim_with_fake_anchor_rejected(dispatched_case: DispatchedCase) -> None:
    # A claim that LOOKS anchored (schema passes) but whose tool_call_id matches no real tool call
    # is rejected by the critic — the anchor must resolve to a genuine audited tool run, not exist.
    run, _ = dispatched_case()
    forged = Claim.model_validate(
        {
            "claim_id": "TASK-932-1",
            "task_id": "TASK-932",
            "status": "confirmed",
            "claim": "Malware persistence key written (forged anchor)",
            "confidence": 0.95,
            "evidence_type": "registry_autostart",
            "source_artifact": "NTUSER.DAT",
            "source_sha256": "e" * 64,  # not a real tool's output hash
            "tool_name": "extract_registry_run_keys",
            "tool_call_id": "TOOL-FAKE-999",  # no such audited tool call
        }
    )
    _write_result(run, "TASK-932", [forged])
    verdicts = {v.task_id: v for v in critique_run(run, settings=load_settings())}
    assert verdicts["TASK-932"].verdict == "retry_required"
    assert "TASK-932-1" not in {c.claim_id for c in read_claims(run.root)}


def _seed_unsupported(run: RunPaths) -> Claim:
    claim = Claim.model_validate(
        {
            "claim_id": "TASK-931-1",
            "task_id": "TASK-931",
            "status": "unsupported",
            "claim": _MARKER,
            "confidence": 0.4,
            "evidence_type": "registry_autostart",
            "source_artifact": None,
            "source_sha256": None,
            "tool_name": None,
            "tool_call_id": None,
        }
    )
    run.unsupported_claims.parent.mkdir(parents=True, exist_ok=True)
    with run.unsupported_claims.open("a", encoding="utf-8") as fh:
        fh.write(claim.model_dump_json() + "\n")
    return claim


def test_unsupported_claim_segregated_in_view(dispatched_case: DispatchedCase) -> None:
    run, evidence = dispatched_case()
    _seed_unsupported(run)
    view = load_report_view(run, evidence_root=evidence)
    ids_unsupported = {c.claim_id for c in view.unsupported}
    ids_findings = {c.claim_id for c in (*view.confirmed, *view.inferred)}
    assert "TASK-931-1" in ids_unsupported
    assert "TASK-931-1" not in ids_findings  # firewall: never merged into findings


def test_unsupported_claim_only_under_appendix_in_report(dispatched_case: DispatchedCase) -> None:
    run, evidence = dispatched_case()
    _seed_unsupported(run)
    report = generate_final_report(run, evidence_root=evidence).read_text(encoding="utf-8")
    assert "Appendix B" in report
    before_appendix, _, after_appendix = report.partition("Appendix B")
    assert _MARKER not in before_appendix  # never presented as a fact in the findings
    assert _MARKER in after_appendix  # disclosed honestly in the rejected appendix
