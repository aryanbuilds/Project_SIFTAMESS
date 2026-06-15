"""J1 - report loader: determinism, graceful-missing, strict/tolerant corruption handling."""

from __future__ import annotations

from pathlib import Path

import pytest
from siftmesh_core.ledgers.claim_ledger import append_claim
from siftmesh_core.reports import ReportLoadError, load_report_view
from siftmesh_core.run_dir import new_run_dir
from siftmesh_core.schemas.claim import Claim


def _claim(cid: str, *, status: str = "confirmed", **over: object) -> Claim:
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
        "tool_call_id": "TOOL-001",
        "supporting_evidence_refs": ["TOOL-001"],
    }
    if status == "unsupported":
        base.update(source_artifact=None, source_sha256=None, tool_name=None, tool_call_id=None)
    base.update(over)
    return Claim.model_validate(base)


def test_view_is_deterministic(dispatched_run) -> None:  # type: ignore[no-untyped-def]
    run, evidence = dispatched_run()
    a = load_report_view(run, evidence_root=evidence)
    b = load_report_view(run, evidence_root=evidence)
    assert a == b  # frozen view → byte-equal structure across calls
    assert a.confirmed  # the real fixture run produced anchored claims
    assert a.manifest is not None and a.has_execution


def test_graceful_missing(tmp_path: Path) -> None:
    run = new_run_dir(base=tmp_path / "case_runs")  # bare run: nothing produced
    view = load_report_view(run)
    assert view.confirmed == () and view.tool_results == () and view.unsupported == ()
    assert view.manifest is None and view.run_state is None
    assert not view.has_execution
    assert any("manifest" in e for e in view.load_errors)


def test_corrupt_line_strict_raises(tmp_path: Path) -> None:
    run = new_run_dir(base=tmp_path / "case_runs")
    run.claim_ledger.write_text('{"not":"a valid claim"}\n', encoding="utf-8")
    with pytest.raises(ReportLoadError):
        load_report_view(run, strict=True)


def test_truncated_final_line_tolerant(tmp_path: Path) -> None:
    run = new_run_dir(base=tmp_path / "case_runs")
    append_claim(run.root, _claim("TASK-001-CLAIM-001"))
    with run.claim_ledger.open("a", encoding="utf-8") as fh:
        fh.write('{"claim_id":"TASK-001-CLAIM-002","tas')  # crash mid-write: truncated, no newline
    with pytest.raises(ReportLoadError):
        load_report_view(run, strict=True)
    view = load_report_view(run, strict=False)
    assert len(view.confirmed) == 1
    assert any("truncated" in e for e in view.load_errors)


def test_unsupported_segregated_in_view(tmp_path: Path) -> None:
    run = new_run_dir(base=tmp_path / "case_runs")
    append_claim(run.root, _claim("TASK-001-CLAIM-001"))
    append_claim(run.root, _claim("TASK-002-CLAIM-001", status="unsupported"))
    view = load_report_view(run)
    assert [c.claim_id for c in view.confirmed] == ["TASK-001-CLAIM-001"]
    assert [c.claim_id for c in view.unsupported] == ["TASK-002-CLAIM-001"]
    # the unsupported claim is NOT in any finding list (the firewall)
    assert all(
        c.status != "unsupported" for c in (*view.confirmed, *view.inferred, *view.contradicted)
    )
