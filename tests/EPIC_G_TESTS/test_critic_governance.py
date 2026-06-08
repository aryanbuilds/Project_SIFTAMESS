"""G7 — the deterministic self-correction GOVERNANCE (crafted inputs, not a live demo).

We construct the INPUTS to the critic (crafted-but-realistic TaskResults over a real
run) and assert OUR critic + decide + retry logic. This is NOT a live agent
self-correction and fabricates no forensic output; the live HERO (a real agent
revises a real over-broad claim) is human-gated (Epic F8) and is not run here.
Also covers CriticVerdict persistence + the Epic-C bare-constructor regression.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from siftmesh_core.config import load_settings
from siftmesh_core.ledgers.claim_ledger import read_claims
from siftmesh_core.ledgers.critic_verdicts import read_critic_verdicts
from siftmesh_core.orchestrator.critic import critique_run
from siftmesh_core.orchestrator.decide import decide
from siftmesh_core.run_dir import RunPaths
from siftmesh_core.schemas.audit import CriticVerdict
from siftmesh_core.schemas.claim import Claim
from siftmesh_core.schemas.task_result import TaskResult

DispatchedCase = Callable[..., tuple[RunPaths, Path]]
_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _result(run: RunPaths, task_id: str, claims: list[Claim], *, attempt: int = 1) -> None:
    tr = TaskResult(
        task_id=task_id,
        profile="claude_headless",
        adapter="claude_headless",
        attempt=attempt,
        status="success",
        tool_call_ids=[],
        claims=claims,
        started_utc=_NOW,
        ended_utc=_NOW,
    )
    run.result_path(task_id).write_text(tr.model_dump_json(indent=2), encoding="utf-8")


def test_governance_sequence_reject_then_accept(dispatched_case: DispatchedCase) -> None:
    run, _ = dispatched_case()
    real = read_claims(run.root)[0]  # a genuinely-anchored claim for the attempt-2 input

    # Attempt 1: a crafted live result with two bad claims (unsupported + bad anchor).
    bad_unsupported = Claim.model_validate(
        {
            "claim_id": "TASK-950-U",
            "task_id": "TASK-950",
            "status": "unsupported",
            "claim": "the attacker used a VPN",
            "confidence": 0.2,
            "evidence_type": "none",
        }
    )
    bad_anchor = Claim.model_validate(
        {
            "claim_id": "TASK-950-B",
            "task_id": "TASK-950",
            "status": "confirmed",
            "claim": "x",
            "confidence": 0.9,
            "evidence_type": "x",
            "source_artifact": "Security.evtx",
            "source_sha256": "a" * 64,
            "tool_name": "t",
            "tool_call_id": "TOOL-999",
        }
    )
    _result(run, "TASK-950", [bad_unsupported, bad_anchor], attempt=1)
    v1 = {v.task_id: v for v in critique_run(run, settings=load_settings())}["TASK-950"]
    assert v1.verdict == "retry_required"
    assert "TASK-950-B" not in {c.claim_id for c in read_claims(run.root)}  # not promoted

    d = decide(v1.verdict, attempt=1, max_attempts=2)
    assert d.action == "retry" and d.tighten_success_criteria

    # Attempt 2: a properly-anchored live claim (reuses a real tool_call_id + manifest anchor).
    good = Claim.model_validate(
        {
            "claim_id": "TASK-950-G",
            "task_id": "TASK-950",
            "status": "confirmed",
            "claim": "a real finding",
            "confidence": 0.9,
            "evidence_type": real.evidence_type,
            "source_artifact": real.source_artifact,
            "source_sha256": real.source_sha256,
            "tool_name": real.tool_name,
            "tool_call_id": real.tool_call_id,
        }
    )
    _result(run, "TASK-950", [good], attempt=2)
    v2 = {v.task_id: v for v in critique_run(run, settings=load_settings())}["TASK-950"]
    assert v2.verdict == "accepted"
    assert "TASK-950-G" in {c.claim_id for c in read_claims(run.root)}  # now promoted


def test_governance_sequence_is_reproducible(dispatched_case: DispatchedCase) -> None:
    # Two independent runs through the same crafted sequence → identical verdict shapes.
    def verdict_shape(run: RunPaths) -> list[tuple[str | None, str]]:
        return [(v.task_id, v.verdict) for v in read_critic_verdicts(run.root)]

    shapes = []
    for _ in range(2):
        run, _ev = dispatched_case()
        critique_run(run, settings=load_settings())
        shapes.append(verdict_shape(run))
    assert shapes[0] == shapes[1]


def test_verdict_round_trips_with_new_fields(dispatched_case: DispatchedCase) -> None:
    run, _ = dispatched_case()
    critique_run(run, settings=load_settings())
    persisted = read_critic_verdicts(run.root)
    assert persisted and all(v.task_id and v.verdict_id and v.decided_utc for v in persisted)


def test_epic_c_bare_verdict_still_constructs() -> None:
    # Regression: the Epic-C bare form (verdict + reasons) must still validate.
    cv = CriticVerdict(verdict="accepted", reasons=["ok"])
    assert cv.affected_claim_ids == [] and cv.task_id is None
