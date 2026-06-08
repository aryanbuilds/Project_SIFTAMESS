"""B6: evidence-handling policy doc generation."""

from __future__ import annotations

from pathlib import Path

from siftmesh_core.evidence.policy import render_evidence_policy, write_evidence_policy
from siftmesh_core.run_dir import new_run_dir


def test_render_contains_standards_and_restriction() -> None:
    text = render_evidence_policy(
        case_id="case01", run_id="RUN-X", evidence_root="/evi", file_count=3
    )
    for token in ("ISO 27037", "SWGDE", "NIST SP 800-86"):
        assert token in text
    assert "read-only" in text.lower()
    assert "court admissibility" in text.lower()  # non-goal stated
    assert "case01" in text
    assert "RUN-X" in text


def test_write_policy_to_context(tmp_path: Path) -> None:
    rp = new_run_dir(base=tmp_path / "runs")
    write_evidence_policy(
        rp.root, case_id="c", run_id=rp.run_id, evidence_root="/evi", file_count=2
    )
    assert rp.evidence_policy.exists()
    assert "Evidence Handling Policy" in rp.evidence_policy.read_text(encoding="utf-8")
