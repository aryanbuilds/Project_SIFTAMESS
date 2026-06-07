"""C2 — Claim firewall: evidence-anchored, or explicitly unsupported."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from siftmesh_core.schemas.claim import Claim, validate_claim_evidence

_HASH = "a" * 64


def _anchored(**over: object) -> dict[str, object]:
    base: dict[str, object] = {
        "claim_id": "CLAIM-001",
        "task_id": "TASK-001",
        "status": "confirmed",
        "claim": "powershell spawned an encoded command",
        "confidence": 0.9,
        "evidence_type": "event_log",
        "source_artifact": "evidence/Security.evtx",
        "source_sha256": _HASH,
        "tool_name": "parse_evtx_security",
        "tool_call_id": "TOOL-001",
    }
    base.update(over)
    return base


def test_confirmed_claim_with_evidence_valid() -> None:
    claim = Claim.model_validate(_anchored())
    assert claim.status == "confirmed"
    assert validate_claim_evidence(claim) == []


def test_claim_requires_evidence_reference() -> None:
    with pytest.raises(ValidationError):
        Claim.model_validate(_anchored(source_sha256=None))


def test_critic_rejects_missing_tool_call_id() -> None:
    # Construction is blocked for an anchored claim...
    with pytest.raises(ValidationError):
        Claim.model_validate(_anchored(tool_call_id=None))
    # ...and the non-raising grader the Critic calls flags it on raw output.
    assert "missing tool_call_id" in validate_claim_evidence(_anchored(tool_call_id=None))


def test_unsupported_claim_allowed_without_evidence() -> None:
    claim = Claim.model_validate(
        {
            "claim_id": "CLAIM-002",
            "task_id": "TASK-001",
            "status": "unsupported",
            "claim": "attacker used a VPN (no artifact found)",
            "confidence": 0.1,
            "evidence_type": "none",
        }
    )
    assert claim.source_sha256 is None
    assert validate_claim_evidence(claim) == []


def test_confidence_out_of_range_rejected() -> None:
    with pytest.raises(ValidationError):
        Claim.model_validate(_anchored(confidence=1.5))


def test_bad_status_rejected() -> None:
    with pytest.raises(ValidationError):
        Claim.model_validate(_anchored(status="totally-true"))


def test_validate_claim_evidence_on_raw_unsupported() -> None:
    assert validate_claim_evidence({"status": "unsupported"}) == []


def test_claim_round_trip_and_utc_z() -> None:
    claim = Claim.model_validate(
        _anchored(timestamp_utc=datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC))
    )
    assert Claim.model_validate_json(claim.model_dump_json()) == claim
    assert json.loads(claim.model_dump_json())["timestamp_utc"] == "2026-01-01T12:00:00Z"
