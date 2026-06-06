"""C6/C10 schemas (pulled forward): validation, round-trip, JSON-Schema, Z-UTC."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from siftmesh_core.schemas import CustodyEvent, EvidenceFile, EvidenceManifest

_HASH = "a" * 64


def _evidence_file() -> EvidenceFile:
    return EvidenceFile(
        path="sub/system.evtx",
        sha256=_HASH,
        size_bytes=10,
        mtime_utc=datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
        evidence_type="evtx",
    )


def test_manifest_round_trip() -> None:
    manifest = EvidenceManifest(
        case_id="case01",
        run_id="RUN-20260101-000000",
        created_utc=datetime(2026, 1, 1, tzinfo=UTC),
        tool_version="0.1.0",
        files=[_evidence_file()],
    )
    restored = EvidenceManifest.model_validate_json(manifest.model_dump_json())
    assert restored == manifest


def test_manifest_serializes_utc_with_z() -> None:
    manifest = EvidenceManifest(
        case_id="c",
        run_id="r",
        created_utc=datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC),
        tool_version="0.1.0",
        files=[_evidence_file()],
    )
    data = json.loads(manifest.model_dump_json())
    assert data["created_utc"] == "2026-01-01T12:00:00Z"
    assert data["files"][0]["mtime_utc"].endswith("Z")


def test_evidence_file_rejects_bad_hash() -> None:
    with pytest.raises(ValidationError):
        EvidenceFile(
            path="x",
            sha256="not-a-hash",
            size_bytes=1,
            mtime_utc=datetime(2026, 1, 1, tzinfo=UTC),
            evidence_type="bin",
        )


def test_manifest_rejects_unknown_field() -> None:
    with pytest.raises(ValidationError):
        EvidenceManifest.model_validate(
            {
                "case_id": "c",
                "run_id": "r",
                "created_utc": datetime(2026, 1, 1, tzinfo=UTC),
                "tool_version": "0.1.0",
                "files": [],
                "bogus": 1,
            }
        )


def test_custody_event_valid_and_z() -> None:
    event = CustodyEvent(
        event_type="evidence_ingested",
        run_id="r",
        artifact="a.evtx",
        source_sha256=_HASH,
        action="hash",
        actor="siftmesh",
        tool_name="hash_utils",
        tool_version="0.1.0",
        start_time_utc=datetime(2026, 1, 1, tzinfo=UTC),
        end_time_utc=datetime(2026, 1, 1, 0, 0, 1, tzinfo=UTC),
        result="ok",
    )
    data = json.loads(event.model_dump_json())
    assert data["event_type"] == "evidence_ingested"
    assert data["start_time_utc"].endswith("Z")
    assert data["parser_version"] is None


def test_custody_event_rejects_bad_event_type() -> None:
    with pytest.raises(ValidationError):
        CustodyEvent.model_validate(
            {
                "event_type": "bogus",
                "run_id": "r",
                "artifact": "a",
                "source_sha256": _HASH,
                "action": "x",
                "actor": "y",
                "tool_name": "t",
                "tool_version": "0.1.0",
                "start_time_utc": datetime(2026, 1, 1, tzinfo=UTC),
                "end_time_utc": datetime(2026, 1, 1, tzinfo=UTC),
                "result": "ok",
            }
        )


def test_json_schema_exportable() -> None:
    for model in (EvidenceManifest, CustodyEvent, EvidenceFile):
        schema = model.model_json_schema()
        assert schema["type"] == "object"
        assert "properties" in schema
