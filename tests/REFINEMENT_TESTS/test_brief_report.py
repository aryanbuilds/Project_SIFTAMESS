"""The final report answers the incident objective from PROMOTED (anchored) findings only."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from siftmesh_core.reports.final_report import generate_final_report
from siftmesh_core.run_dir import RunPaths
from siftmesh_core.schemas.evidence import EvidenceManifest

MakeRealRun = Callable[..., tuple[RunPaths, Path]]


def _set_objective(run: RunPaths, objective: str) -> None:
    manifest = EvidenceManifest.model_validate_json(
        run.evidence_manifest.read_text(encoding="utf-8")
    )
    manifest = manifest.model_copy(update={"incident_objective": objective})
    run.evidence_manifest.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")


def test_report_answers_objective_with_findings(make_real_run: MakeRealRun) -> None:
    run, evidence = make_real_run(dispatch=True, critique=True)
    objective = "Determine whether host ROCBA was compromised and the initial access vector."
    _set_objective(run, objective)

    body = generate_final_report(run, evidence_root=evidence).read_text(encoding="utf-8")
    assert "## Answer to the incident objective" in body
    assert objective in body
    # The section sits before the unsupported appendix, and never pulls from it (firewall).
    assert body.index("## Answer to the incident objective") < body.index("Appendix B")


def test_no_objective_no_section(make_real_run: MakeRealRun) -> None:
    run, evidence = make_real_run(dispatch=True, critique=True)
    body = generate_final_report(run, evidence_root=evidence).read_text(encoding="utf-8")
    assert "Answer to the incident objective" not in body


def test_objective_with_no_findings_states_gap(make_real_run: MakeRealRun) -> None:
    # A planned-only run has no promoted claims; the section must still appear and say so.
    run, evidence = make_real_run(plan=True)
    _set_objective(run, "Was ROCBA compromised?")
    body = generate_final_report(run, evidence_root=evidence).read_text(encoding="utf-8")
    assert "## Answer to the incident objective" in body
    assert "No evidence-anchored finding yet bears on this objective" in body
