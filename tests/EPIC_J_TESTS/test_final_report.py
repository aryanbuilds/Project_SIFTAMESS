"""J3 — final report: sections, anchors, byte-stability, the unsupported firewall, empty run."""

from __future__ import annotations

from pathlib import Path

from siftmesh_core.ledgers.claim_ledger import append_claim
from siftmesh_core.reports import generate_final_report, load_report_view, split_body
from siftmesh_core.reports.final_report import generate_final_report as _gen  # explicit
from siftmesh_core.run_dir import new_run_dir
from siftmesh_core.schemas.claim import Claim


def _claim(
    cid: str, *, status: str = "confirmed", claim: str | None = None, **over: object
) -> Claim:
    base: dict[str, object] = {
        "claim_id": cid,
        "task_id": cid.split("-CLAIM")[0],
        "status": status,
        "claim": claim or f"finding {cid}",
        "confidence": 0.9,
        "evidence_type": "registry_autostart",
        "source_artifact": "evidence/extracted/SOFTWARE",
        "source_sha256": "b" * 64,
        "tool_name": "extract_registry_run_keys",
        "tool_call_id": "TOOL-003",
        "supporting_evidence_refs": ["TOOL-003"],
    }
    if status == "unsupported":
        base.update(source_artifact=None, source_sha256=None, tool_name=None, tool_call_id=None)
    base.update(over)
    return Claim.model_validate(base)


def test_final_report_sections_and_anchors(dispatched_run) -> None:  # type: ignore[no-untyped-def]
    run, evidence = dispatched_run()
    path = generate_final_report(run, evidence_root=evidence)
    assert path == run.reports / "final_report.md"
    body = split_body(path.read_text(encoding="utf-8"))
    for heading in (
        "Executive summary",
        "Confirmed findings",
        "MITRE ATT&CK mapping",
        "Appendix A — tool-execution log",
        "Appendix B — unsupported claims",
        "Limitations",
    ):
        assert heading in body, heading
    assert "NOT a claim of court" in body
    # the tool-execution appendix lists EVERY tool call (traceability, uncapped)
    view = load_report_view(run, evidence_root=evidence)
    assert view.tool_results  # the real run made tool calls
    for t in view.tool_results:
        assert t.tool_call_id in body
    # confirmed findings carry their evidence anchor
    for c in view.confirmed[:1]:
        assert c.tool_call_id in body and (c.source_sha256 or "")[:16] in body


def test_final_report_body_byte_stable(dispatched_run) -> None:  # type: ignore[no-untyped-def]
    run, evidence = dispatched_run()
    first = split_body(
        generate_final_report(run, evidence_root=evidence).read_text(encoding="utf-8")
    )
    second = split_body(_gen(run, evidence_root=evidence).read_text(encoding="utf-8"))
    assert first == second  # same ledgers → byte-identical body (only the header timestamp differs)
    assert "\r" not in first
    assert "generated_utc" not in first  # the timestamp lives in the excluded header only


def test_unsupported_never_in_findings(tmp_path: Path) -> None:
    run = new_run_dir(base=tmp_path / "case_runs")
    append_claim(run.root, _claim("TASK-001-CLAIM-001", claim="REAL confirmed autostart entry"))
    append_claim(
        run.root,
        _claim(
            "TASK-002-CLAIM-001",
            status="unsupported",
            claim="HALLUCINATED lateral movement to 10.0.0.5",
        ),
    )
    body = split_body(generate_final_report(run).read_text(encoding="utf-8"))
    appendix_idx = body.index("Appendix B — unsupported claims")
    findings_region = body[:appendix_idx]
    assert "HALLUCINATED lateral movement" not in findings_region  # never a fact
    assert "HALLUCINATED lateral movement" in body[appendix_idx:]  # only in the rejected appendix
    assert "REAL confirmed autostart" in findings_region


def test_empty_run_does_not_crash(planned_run) -> None:  # type: ignore[no-untyped-def]
    run, evidence = planned_run()
    body = split_body(
        generate_final_report(run, evidence_root=evidence).read_text(encoding="utf-8")
    )
    assert "No analytic execution recorded" in body
    assert "Limitations" in body  # mandatory section still present
