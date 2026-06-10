"""Incident-brief intake — TRUSTED objective extraction, fail-closed, deterministic.

Public synthetic fixtures only; no SANS evidence, no live agent (CLAUDE §2B).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from siftmesh_core.intake.brief import (
    SUPPORTED_SUFFIXES,
    BriefIntakeError,
    derive_objective,
    extract_brief_text,
    ingest_brief,
)
from siftmesh_core.run_dir import new_run_dir

BRIEF_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "brief"


def test_supported_suffixes() -> None:
    assert SUPPORTED_SUFFIXES == (".txt", ".md", ".pptx", ".docx", ".pdf")


def test_extract_txt_and_md() -> None:
    for name in ("objective.txt", "objective.md"):
        text = extract_brief_text(BRIEF_FIXTURES / name)
        assert "ROCBA" in text
        assert "compromised" in text.lower()
        assert "exfiltration" in text.lower()


def test_derive_objective_deterministic_and_bounded() -> None:
    raw = "  Determine whether host ROCBA\twas\n\ncompromised.   Identify the vector.  "
    out = derive_objective(raw)
    assert out == derive_objective(raw)  # deterministic
    assert "\n" not in out and "\t" not in out  # whitespace collapsed
    assert out == "Determine whether host ROCBA was compromised. Identify the vector."


def test_derive_objective_truncates_at_boundary() -> None:
    long = "Sentence one. " + ("word " * 500)
    out = derive_objective(long, max_chars=100)
    assert len(out) <= 110  # bounded (+ the " […]" marker)
    assert out.endswith("[…]")


def test_unsupported_suffix_fails_closed(tmp_path: Path) -> None:
    bad = tmp_path / "brief.xyz"
    bad.write_text("hi", encoding="utf-8")
    with pytest.raises(BriefIntakeError, match="unsupported"):
        extract_brief_text(bad)


def test_missing_file_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(BriefIntakeError, match="not found"):
        extract_brief_text(tmp_path / "nope.txt")


def test_empty_brief_fails_closed(tmp_path: Path) -> None:
    empty = tmp_path / "empty.md"
    empty.write_text("   \n\t \n", encoding="utf-8")
    with pytest.raises(BriefIntakeError, match="no extractable text"):
        extract_brief_text(empty)


def test_missing_pptx_lib_fails_closed_not_crash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Force `from pptx import Presentation` to raise ImportError regardless of install state.
    monkeypatch.setitem(sys.modules, "pptx", None)
    pptx = tmp_path / "brief.pptx"
    pptx.write_bytes(b"PK\x03\x04stub")  # a file must exist; the import fails before parsing
    with pytest.raises(BriefIntakeError, match="python-pptx"):
        extract_brief_text(pptx)


def test_pptx_roundtrip_when_lib_present(tmp_path: Path) -> None:
    pptx_mod = pytest.importorskip("pptx")  # skips unless `uv sync --extra brief`
    prs = pptx_mod.Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[5])
    slide.shapes.title.text = "Operation ROCBA objective: find initial access"
    out = tmp_path / "brief.pptx"
    prs.save(str(out))
    assert "initial access" in extract_brief_text(out)


def test_ingest_brief_writes_trusted_markdown(tmp_path: Path) -> None:
    run = new_run_dir(base=tmp_path / "case_runs")
    path, objective = ingest_brief(BRIEF_FIXTURES / "objective.md", run)
    assert path == run.incident_brief
    assert objective and "ROCBA" in objective
    body = path.read_text(encoding="utf-8")
    assert "TRUSTED operator context" in body
    assert "Full briefing (verbatim)" in body
    assert objective in body
    # The ingest is visible in the audit (visibility, not a trust change).
    assert "incident_brief_ingested" in run.orchestration_events.read_text(encoding="utf-8")
