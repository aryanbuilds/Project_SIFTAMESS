"""The brief is recorded as manifest METADATA, never added to the hostile evidence set."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from siftmesh_core.evidence.vault import init_case
from siftmesh_core.intake.brief import BriefIntakeError
from siftmesh_core.schemas.evidence import EvidenceManifest

BRIEF_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "brief"


def test_init_case_records_brief_as_metadata_only(
    tmp_path: Path, build_evidence: Callable[..., None]
) -> None:
    evidence = tmp_path / "evidence"
    build_evidence(evidence)
    brief = tmp_path / "objective.md"  # operator-supplied, OUTSIDE the evidence dir
    brief.write_bytes((BRIEF_FIXTURES / "objective.md").read_bytes())

    run = init_case(tmp_path / "case", evidence, brief_path=brief)

    manifest = EvidenceManifest.model_validate_json(
        run.evidence_manifest.read_text(encoding="utf-8")
    )
    assert manifest.incident_objective and "ROCBA" in manifest.incident_objective
    assert manifest.incident_brief_path == "context/incident_brief.md"
    assert run.incident_brief.is_file()
    # The brief is NEVER in the hostile evidence set (the artifact router consumes `files`).
    assert all("incident_brief" not in f.path for f in manifest.files)
    assert all(not f.path.endswith("objective.md") for f in manifest.files)


def test_no_brief_leaves_fields_none(tmp_path: Path, build_evidence: Callable[..., None]) -> None:
    evidence = tmp_path / "evidence"
    build_evidence(evidence)
    run = init_case(tmp_path / "case", evidence)
    manifest = EvidenceManifest.model_validate_json(
        run.evidence_manifest.read_text(encoding="utf-8")
    )
    assert manifest.incident_objective is None
    assert manifest.incident_brief_path is None
    assert not run.incident_brief.exists()


def test_unreadable_brief_aborts_init_case(
    tmp_path: Path, build_evidence: Callable[..., None]
) -> None:
    evidence = tmp_path / "evidence"
    build_evidence(evidence)
    bad = tmp_path / "brief.xyz"
    bad.write_text("nope", encoding="utf-8")
    try:
        init_case(tmp_path / "case", evidence, brief_path=bad)
    except BriefIntakeError:
        return
    raise AssertionError("init_case should fail closed on an unreadable brief")


def test_init_case_with_inline_objective(
    tmp_path: Path, build_evidence: Callable[..., None]
) -> None:
    evidence = tmp_path / "evidence"
    build_evidence(evidence)
    run = init_case(
        tmp_path / "case", evidence, objective_text="Was host ROCBA compromised? Find the vector."
    )
    manifest = EvidenceManifest.model_validate_json(
        run.evidence_manifest.read_text(encoding="utf-8")
    )
    assert manifest.incident_objective == "Was host ROCBA compromised? Find the vector."
    assert manifest.incident_brief_path == "context/incident_brief.md"
    assert run.incident_brief.is_file()
    assert all("incident_brief" not in f.path for f in manifest.files)


def test_init_case_rejects_brief_and_objective_together(
    tmp_path: Path, build_evidence: Callable[..., None]
) -> None:
    evidence = tmp_path / "evidence"
    build_evidence(evidence)
    brief = tmp_path / "objective.md"
    brief.write_bytes((BRIEF_FIXTURES / "objective.md").read_bytes())
    try:
        init_case(tmp_path / "case", evidence, brief_path=brief, objective_text="also this")
    except BriefIntakeError:
        return
    raise AssertionError("init_case should reject --brief and --objective together")
