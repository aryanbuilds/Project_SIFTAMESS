"""J7 replay (text + self-contained HTML) and J4 accuracy report (self-assessment + diff mode)."""

from __future__ import annotations

from pathlib import Path

from siftmesh_core.ledgers.claim_ledger import append_claim
from siftmesh_core.reports import (
    generate_accuracy_report,
    generate_replay_html,
    load_report_view,
    render_text_replay,
    split_body,
)
from siftmesh_core.run_dir import new_run_dir
from siftmesh_core.schemas.claim import Claim


def _claim(cid: str, *, claim: str, status: str = "confirmed") -> Claim:
    base: dict[str, object] = {
        "claim_id": cid,
        "task_id": cid.split("-CLAIM")[0],
        "status": status,
        "claim": claim,
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
    return Claim.model_validate(base)


def test_replay_text_deterministic(dispatched_run) -> None:  # type: ignore[no-untyped-def]
    run, evidence = dispatched_run()
    view = load_report_view(run, evidence_root=evidence)
    a = render_text_replay(view)
    b = render_text_replay(view)
    assert a == b
    assert run.run_id in a and "orchestration events" in a
    assert view.events  # the real run logged events


def test_replay_html_self_contained_and_stable(dispatched_run) -> None:  # type: ignore[no-untyped-def]
    run, evidence = dispatched_run()
    view = load_report_view(run, evidence_root=evidence)
    path = generate_replay_html(run, view=view)
    assert path == run.reports / "replay.html"
    text = path.read_text(encoding="utf-8")
    body = split_body(text)
    # self-contained: no external assets
    assert "<script src" not in text and "http://" not in body and "https://" not in body
    # byte-stable body across renders
    assert split_body(generate_replay_html(run, view=view).read_text(encoding="utf-8")) == body


def test_accuracy_self_assessment_no_fabricated_metrics(dispatched_run) -> None:  # type: ignore[no-untyped-def]
    run, evidence = dispatched_run()
    body = split_body(
        generate_accuracy_report(run, evidence_root=evidence).read_text(encoding="utf-8")
    )
    assert "self-assessment" in body
    assert "Confidence distribution" in body
    assert "Precision" not in body  # never fabricate precision/recall without ground truth


def test_accuracy_diff_mode_with_ground_truth(tmp_path: Path) -> None:
    run = new_run_dir(base=tmp_path / "case_runs")
    append_claim(
        run.root,
        _claim("TASK-001-CLAIM-001", claim="powershell scriptblock executed CL_Utility.ps1"),
    )
    expected = tmp_path / "expected.md"
    expected.write_text(
        "# Expected findings\n"
        "- powershell scriptblock executed CL_Utility.ps1\n"
        "- a finding never produced\n",
        encoding="utf-8",
    )
    body = split_body(
        generate_accuracy_report(run, expected_findings=expected).read_text(encoding="utf-8")
    )
    assert "Precision" in body and "True positives" in body
    assert "a finding never produced" in body  # listed as a false negative
