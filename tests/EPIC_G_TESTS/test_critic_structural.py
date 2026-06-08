"""G1/G2/G3 — structural critic verdicts, ledgers, and the clean-floor no-op."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from siftmesh_core.config import load_settings
from siftmesh_core.ledgers.claim_ledger import read_claims
from siftmesh_core.ledgers.critic_verdicts import read_critic_verdicts
from siftmesh_core.orchestrator.critic import critique_run
from siftmesh_core.run_dir import RunPaths
from siftmesh_core.schemas.claim import Claim
from siftmesh_core.schemas.task_result import TaskResult

DispatchedCase = Callable[..., tuple[RunPaths, Path]]


def _write_result(run: RunPaths, task_id: str, *, claims: list[Claim], adapter: str) -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    tr = TaskResult(
        task_id=task_id,
        profile=adapter,
        adapter=adapter,
        attempt=1,
        status="success",
        tool_call_ids=[c.tool_call_id for c in claims if c.tool_call_id],
        claims=claims,
        started_utc=now,
        ended_utc=now,
    )
    run.result_path(task_id).write_text(tr.model_dump_json(indent=2), encoding="utf-8")


def _live_claim(task_id: str, **over: object) -> Claim:
    base: dict[str, object] = {
        "claim_id": f"{task_id}-LIVE-1",
        "task_id": task_id,
        "status": "confirmed",
        "claim": "a logon occurred",
        "confidence": 0.9,
        "evidence_type": "windows_event_log",
        "source_artifact": "Security.evtx",
        "source_sha256": "a" * 64,
        "tool_name": "parse_evtx_security",
        "tool_call_id": "TOOL-999",
    }
    base.update(over)
    return Claim.model_validate(base)


def test_clean_floor_run_all_accepted_no_rewrites(dispatched_case: DispatchedCase) -> None:
    run, _ = dispatched_case()
    before = len(read_claims(run.root))
    verdicts = critique_run(run, settings=load_settings())
    assert verdicts and all(v.verdict == "accepted" for v in verdicts)
    # double-write guard: the critic re-appended NOTHING (floor claims already persisted)
    assert len(read_claims(run.root)) == before
    # one verdict per task, persisted + fully populated
    persisted = read_critic_verdicts(run.root)
    assert len(persisted) == len(verdicts)
    assert all(v.task_id and v.verdict_id and v.decided_utc for v in persisted)


def test_critic_rejects_missing_tool_call_id(dispatched_case: DispatchedCase) -> None:
    # A crafted LIVE result whose claim's tool_call_id is absent from the real ledger.
    run, _ = dispatched_case()
    _write_result(run, "TASK-901", claims=[_live_claim("TASK-901")], adapter="claude_headless")
    verdicts = {v.task_id: v for v in critique_run(run, settings=load_settings())}
    v = verdicts["TASK-901"]
    assert v.verdict == "retry_required"
    assert "TASK-901-LIVE-1" in v.affected_claim_ids
    # the bad claim was NOT promoted to the findings ledger
    assert "TASK-901-LIVE-1" not in {c.claim_id for c in read_claims(run.root)}


def test_unsupported_lands_in_unsupported_not_findings(dispatched_case: DispatchedCase) -> None:
    from siftmesh_core.ledgers.claim_ledger import read_unsupported_claims

    run, _ = dispatched_case()
    claim = _live_claim(
        "TASK-902",
        claim_id="TASK-902-U",
        status="unsupported",
        source_artifact=None,
        source_sha256=None,
        tool_name=None,
        tool_call_id=None,
    )
    _write_result(run, "TASK-902", claims=[claim], adapter="claude_headless")
    critique_run(run, settings=load_settings())
    assert "TASK-902-U" in {c.claim_id for c in read_unsupported_claims(run.root)}
    assert "TASK-902-U" not in {c.claim_id for c in read_claims(run.root)}
