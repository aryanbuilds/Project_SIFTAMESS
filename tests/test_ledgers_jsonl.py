"""C7 — generic JSONL ledger + claim routing (validate-before-write)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from siftmesh_core.ledgers.claim_ledger import (
    append_claim,
    read_claims,
    read_unsupported_claims,
)
from siftmesh_core.ledgers.jsonl_ledger import (
    LedgerCorruptionError,
    append_record,
    read_records,
)
from siftmesh_core.ledgers.tool_call_ledger import append_tool_result, read_tool_results
from siftmesh_core.schemas.claim import Claim
from siftmesh_core.schemas.tool_result import ToolResult

_HASH = "c" * 64


def _claim(claim_id: str, status: str = "confirmed") -> Claim:
    fields: dict[str, object] = {
        "claim_id": claim_id,
        "task_id": "TASK-001",
        "status": status,
        "claim": "x",
        "confidence": 0.5,
        "evidence_type": "event_log",
    }
    if status != "unsupported":
        fields.update(
            source_artifact="evidence/a.evtx",
            source_sha256=_HASH,
            tool_name="t",
            tool_call_id="TOOL-1",
        )
    return Claim.model_validate(fields)


def test_generic_ledger_round_trip(tmp_path: Path) -> None:
    claims = [_claim("CLAIM-1"), _claim("CLAIM-2")]
    rel = Path("claims") / "claim_ledger.jsonl"
    for claim in claims:
        append_record(tmp_path, rel, claim)
    assert list(read_records(tmp_path / rel, Claim)) == claims


def test_read_missing_ledger_is_empty(tmp_path: Path) -> None:
    assert list(read_records(tmp_path / "claims" / "nope.jsonl", Claim)) == []


def test_corrupt_line_raises_not_skipped(tmp_path: Path) -> None:
    target = tmp_path / "claims" / "claim_ledger.jsonl"
    target.parent.mkdir(parents=True)
    target.write_text('{"not":"a valid claim"}\n', encoding="utf-8")
    with pytest.raises(LedgerCorruptionError):
        list(read_records(target, Claim))


def test_blank_line_raises_not_skipped(tmp_path: Path) -> None:
    target = tmp_path / "claims" / "claim_ledger.jsonl"
    target.parent.mkdir(parents=True)
    target.write_text("\n", encoding="utf-8")
    with pytest.raises(LedgerCorruptionError):
        list(read_records(target, Claim))


def test_claim_routing_unsupported_isolated(tmp_path: Path) -> None:
    append_claim(tmp_path, _claim("CLAIM-1", "confirmed"))
    append_claim(tmp_path, _claim("CLAIM-9", "unsupported"))
    findings = read_claims(tmp_path)
    unsupported = read_unsupported_claims(tmp_path)
    assert [c.claim_id for c in findings] == ["CLAIM-1"]
    assert [c.claim_id for c in unsupported] == ["CLAIM-9"]
    assert all(c.status != "unsupported" for c in findings)


def test_tool_call_ledger_round_trip(tmp_path: Path) -> None:
    result = ToolResult(
        tool_call_id="TOOL-1",
        source_artifact="evidence/a.evtx",
        source_sha256=_HASH,
        start_time_utc=datetime(2026, 1, 1, tzinfo=UTC),
        end_time_utc=datetime(2026, 1, 1, 0, 0, 1, tzinfo=UTC),
        status="success",
        backend="evtx",
        tool_version="0.1.0",
    )
    append_tool_result(tmp_path, result)
    assert read_tool_results(tmp_path) == [result]
