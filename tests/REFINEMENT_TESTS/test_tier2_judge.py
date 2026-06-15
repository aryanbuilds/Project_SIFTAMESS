"""Advisory Tier-2 LLM judge (G8): may lower confidence / flag corroboration / annotate - NEVER
promotes. Tier-1 deterministic code stays the sole promoter. Agent subprocess is mocked.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from siftmesh_core.config import load_settings
from siftmesh_core.ledgers.claim_ledger import read_claims
from siftmesh_core.orchestrator import critic as critic_mod
from siftmesh_core.orchestrator.critic import run_tier2_judge
from siftmesh_core.run_dir import RunPaths

MakeRealRun = Callable[..., tuple[RunPaths, Path]]


def _judge_reply(claim_id: str) -> str:
    return json.dumps(
        {
            "judgements": [
                {
                    "claim_id": claim_id,
                    "verdict": "low_confidence",
                    "note": "single source",
                    "suggested_confidence": 0.3,
                },
                {  # a fabricated id must be ignored, never acted on
                    "claim_id": "TASK-999-CLAIM-999",
                    "verdict": "overbroad",
                    "note": "fake",
                    "suggested_confidence": 0.1,
                },
            ]
        }
    )


def test_tier2_lowers_confidence_and_never_promotes(
    make_real_run: MakeRealRun, monkeypatch
) -> None:
    run, evidence = make_real_run(dispatch=True, critique=True)
    before = read_claims(run.root)
    assert before, "need promoted claims to judge"
    target = before[0]
    monkeypatch.setattr(
        critic_mod, "invoke_judge_text", lambda *a, **k: _judge_reply(target.claim_id)
    )

    acted = run_tier2_judge(
        run, settings=load_settings(), evidence_root=evidence, audit=_audit(run)
    )
    assert acted == 1  # only the real claim_id acted on; the fabricated one ignored

    # advisory confidence DOWNGRADE logged; the ledger claim set is UNCHANGED (no promote/remove)
    after = read_claims(run.root)
    assert {c.claim_id for c in after} == {c.claim_id for c in before}
    changes = run.confidence_changes.read_text(encoding="utf-8")
    assert target.claim_id in changes and "tier2 advisory" in changes
    judged = run.tier2_judgements.read_text(encoding="utf-8").splitlines()
    assert any(target.claim_id in line for line in judged)
    assert "TASK-999-CLAIM-999" not in run.confidence_changes.read_text(encoding="utf-8")


def test_tier2_cannot_raise_confidence(make_real_run: MakeRealRun, monkeypatch) -> None:
    run, evidence = make_real_run(dispatch=True, critique=True)
    target = read_claims(run.root)[0]
    reply = json.dumps(
        {
            "judgements": [
                {
                    "claim_id": target.claim_id,
                    "verdict": "low_confidence",
                    "suggested_confidence": 0.999,  # ABOVE current → must be refused
                }
            ]
        }
    )
    monkeypatch.setattr(critic_mod, "invoke_judge_text", lambda *a, **k: reply)
    run_tier2_judge(run, settings=load_settings(), evidence_root=evidence, audit=_audit(run))
    # judgement is logged, but NO confidence change was written (cannot raise)
    assert not run.confidence_changes.exists() or "tier2" not in run.confidence_changes.read_text(
        encoding="utf-8"
    )


def test_tier2_failsoft_when_agent_absent(make_real_run: MakeRealRun, monkeypatch) -> None:
    run, evidence = make_real_run(dispatch=True, critique=True)
    monkeypatch.setattr(critic_mod, "invoke_judge_text", lambda *a, **k: None)
    assert (
        run_tier2_judge(run, settings=load_settings(), evidence_root=evidence, audit=_audit(run))
        == 0
    )


def test_tier2_tolerates_markdown_fenced_json(make_real_run: MakeRealRun, monkeypatch) -> None:
    # Real judges (gemini/codex/opencode) routinely wrap JSON in ```json fences - a well-formed
    # opinion must NOT be silently dropped over a fence (regression: live opencode judge 2026-06).
    run, evidence = make_real_run(dispatch=True, critique=True)
    target = read_claims(run.root)[0]
    body = json.dumps(
        {
            "judgements": [
                {
                    "claim_id": target.claim_id,
                    "verdict": "overbroad",
                    "note": "fenced",
                    "suggested_confidence": 0.2,
                }
            ]
        }
    )
    monkeypatch.setattr(critic_mod, "invoke_judge_text", lambda *a, **k: f"```json\n{body}\n```")
    acted = run_tier2_judge(
        run, settings=load_settings(), evidence_root=evidence, audit=_audit(run)
    )
    assert acted == 1  # fenced JSON parsed, not dropped
    assert target.claim_id in run.tier2_judgements.read_text(encoding="utf-8")


def test_tier2_logs_unparsable_response(make_real_run: MakeRealRun, monkeypatch) -> None:
    # A genuinely non-JSON judge reply must be VISIBLE in the audit (not a silent return 0).
    run, evidence = make_real_run(dispatch=True, critique=True)
    monkeypatch.setattr(critic_mod, "invoke_judge_text", lambda *a, **k: "Sorry, no JSON here.")
    acted = run_tier2_judge(
        run, settings=load_settings(), evidence_root=evidence, audit=_audit(run)
    )
    assert acted == 0
    assert "tier2_judge_unparsable" in run.orchestration_events.read_text(encoding="utf-8")


def _audit(run: RunPaths):  # type: ignore[no-untyped-def]
    from siftmesh_core.ledgers.audit_log import open_orchestration_log

    return open_orchestration_log(run.orchestration_events, run.run_id)
