"""M3 — golden report-body tests over the committed recorded-golden run (criterion 5).

The recorded run (tests/golden/recorded_run/RUN-GOLDEN) holds REAL ledgers produced once by
the real Epic-D tools over the committed fixtures (§2B recorded-golden floor). These tests
prove Epic J's claim: reports are byte-deterministic pure functions of the ledgers — the
header (timestamp/host/run_dir) is volatile by design and excluded via the sentinel split.

Regen ONLY via:  uv run python tests/golden/record.py --update   (review the diff, commit).
"""

from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path

import pytest
from siftmesh_core.reports import generate_all_reports
from siftmesh_core.reports.loader import load_report_view
from siftmesh_core.reports.render import split_body
from siftmesh_core.reports.replay import render_text_replay
from siftmesh_core.run_dir import RunPaths

GOLDEN = Path(__file__).resolve().parents[1] / "golden"
RECORDED = GOLDEN / "recorded_run" / "RUN-GOLDEN"
BODIES = GOLDEN / "bodies"
REPORTS = (
    "final_report.md",
    "accuracy_report.md",
    "dataset_documentation.md",
    "architecture_notes.md",
    "replay.html",
)
_REGEN = "regen via: uv run python tests/golden/record.py --update (then review the diff)"

MakeRealRun = Callable[..., tuple[RunPaths, Path]]


def _render_from_recorded(tmp_path: Path, sub: str) -> dict[str, str]:
    """Copy the committed run, drop its reports, re-render, return name -> body."""
    # The copy keeps the dir name RUN-GOLDEN: RunPaths derives run_id from it, and the
    # bodies embed the run_id (recorded with exactly this name).
    work = tmp_path / sub / RECORDED.name
    shutil.copytree(RECORDED, work)
    shutil.rmtree(work / "reports")
    run = RunPaths(root=work)
    generate_all_reports(run)
    bodies = {
        name: split_body((work / "reports" / name).read_text(encoding="utf-8")) for name in REPORTS
    }
    bodies["replay.txt"] = render_text_replay(load_report_view(run))
    return bodies


@pytest.mark.parametrize("name", [*REPORTS, "replay.txt"])
def test_recorded_golden_body_byte_stable(tmp_path: Path, name: str) -> None:
    # Rendering the COMMITTED ledgers reproduces the COMMITTED body byte-for-byte.
    rendered = _render_from_recorded(tmp_path, "render1")[name]
    golden = (BODIES / name).read_text(encoding="utf-8")
    assert rendered == golden, f"{name} drifted from its golden body — {_REGEN}"


def test_double_render_identical(tmp_path: Path) -> None:
    # Two independent renders of identical ledgers are byte-identical (J determinism, M3).
    first = _render_from_recorded(tmp_path, "a")
    second = _render_from_recorded(tmp_path, "b")
    assert first == second


def test_fresh_run_double_render_identical(tmp_path: Path, make_real_run: MakeRealRun) -> None:
    # Env-independence: a FRESH real run (new timestamps, new paths) also double-renders
    # byte-identically — determinism is a property of the pipeline, not of the fixture.
    run, evidence = make_real_run(dispatch=True, critique=True)
    generate_all_reports(run, evidence_root=evidence)
    first = {n: split_body((run.root / "reports" / n).read_text(encoding="utf-8")) for n in REPORTS}
    generate_all_reports(run, evidence_root=evidence)
    second = {
        n: split_body((run.root / "reports" / n).read_text(encoding="utf-8")) for n in REPORTS
    }
    assert first == second


def test_recorded_run_is_host_independent() -> None:
    # The committed run must never embed an absolute host path (re-record normalizes).
    for p in RECORDED.rglob("*"):
        if p.is_file():
            text = p.read_text(encoding="utf-8", errors="ignore")
            assert "/tmp/" not in text, f"absolute path leaked in {p.name} — {_REGEN}"
