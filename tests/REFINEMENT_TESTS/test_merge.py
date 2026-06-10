"""Cross-run merge: deterministic combined report + opt-in validated agent synthesis (PLAN 11)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from siftmesh_core.config import load_settings
from siftmesh_core.reports import merge_runs
from siftmesh_core.reports.render import split_body
from siftmesh_core.run_dir import RunPaths
from siftmesh_core.schemas.evidence import EvidenceManifest

MakeRealRun = Callable[..., tuple[RunPaths, Path]]


def _set_objective(run: RunPaths, objective: str) -> None:
    m = EvidenceManifest.model_validate_json(run.evidence_manifest.read_text("utf-8"))
    run.evidence_manifest.write_text(
        m.model_copy(update={"incident_objective": objective}).model_dump_json(indent=2), "utf-8"
    )


def test_merge_combines_runs_with_provenance(tmp_path: Path, make_real_run: MakeRealRun) -> None:
    run_a, _ = make_real_run(dispatch=True, critique=True)
    run_b, _ = make_real_run(dispatch=True, critique=True)
    _set_objective(run_a, "Was host ROCBA compromised and how?")

    merged = merge_runs(
        tmp_path / "case_merged", [run_a.root, run_b.root], settings=load_settings()
    )
    body = split_body((merged.reports / "final_report.md").read_text("utf-8"))
    assert "Cross-Run Merged Report" in body
    assert run_a.run_id in body and run_b.run_id in body  # per-run provenance
    assert "Answer to the incident objective" in body
    assert "Was host ROCBA compromised" in body
    # merged_claims.jsonl carries source_run provenance per claim
    merged_claims = (merged.claims / "merged_claims.jsonl").read_text("utf-8").splitlines()
    assert merged_claims and all("source_run" in line for line in merged_claims)


def test_merge_requires_two_runs(tmp_path: Path, make_real_run: MakeRealRun) -> None:
    run_a, _ = make_real_run(dispatch=True, critique=True)
    with pytest.raises(ValueError, match="at least two"):
        merge_runs(tmp_path / "m", [run_a.root], settings=load_settings())


def test_agent_synthesis_validates_claim_refs(
    tmp_path: Path, make_real_run: MakeRealRun, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_a, _ = make_real_run(dispatch=True, critique=True)
    run_b, _ = make_real_run(dispatch=True, critique=True)

    # First mocked agent reply cites a FABRICATED id → rejected; retry returns a clean reply.
    from siftmesh_core.reports import merge_report

    replies = iter(
        [
            "Per RUN-FAKE:TASK-999-CLAIM-001 the host was owned.",  # unknown id → reject
            "The runs corroborate program execution and registry autostart activity.",  # clean
        ]
    )
    monkeypatch.setattr(merge_report, "invoke_claude_text", lambda *a, **k: next(replies, None))
    merged = merge_runs(
        tmp_path / "m", [run_a.root, run_b.root], settings=load_settings(), agent_synthesis=True
    )
    body = split_body((merged.reports / "final_report.md").read_text("utf-8"))
    assert "analyst synthesis" in body.lower()
    assert "RUN-FAKE" not in body  # the fabricated-id reply was rejected, never rendered


def test_agent_synthesis_failsoft_when_agent_unavailable(
    tmp_path: Path, make_real_run: MakeRealRun, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_a, _ = make_real_run(dispatch=True, critique=True)
    run_b, _ = make_real_run(dispatch=True, critique=True)
    from siftmesh_core.reports import merge_report

    monkeypatch.setattr(merge_report, "invoke_claude_text", lambda *a, **k: None)  # absent
    merged = merge_runs(
        tmp_path / "m", [run_a.root, run_b.root], settings=load_settings(), agent_synthesis=True
    )
    body = split_body((merged.reports / "final_report.md").read_text("utf-8"))
    assert "Cross-Run Merged Report" in body  # deterministic report still complete
    assert "analyst synthesis" not in body.lower()  # no synthesis section (fail-soft)
