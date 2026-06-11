"""Pre-run readiness synthesis (TUI wizard) — verify + space → recommendation/portions. Headless."""

from __future__ import annotations

import zipfile
from pathlib import Path

from siftmesh_core.config import load_settings
from siftmesh_core.tui.space_view import build_readiness


def _evidence_with_zip(tmp_path: Path, payload: bytes) -> Path:
    ev = tmp_path / "ev"
    ev.mkdir()
    zp = ev / "mem.zip"
    with zipfile.ZipFile(zp, "w") as z:
        z.writestr("image.raw", payload)  # zip header gives an EXACT derived estimate
    return ev


def test_readiness_fits_recommends_full_or_single(tmp_path: Path) -> None:
    ev = _evidence_with_zip(tmp_path, b"x" * 1024)  # tiny → always fits free disk
    report = build_readiness(ev, run_location=tmp_path, settings=load_settings())
    assert report.fits is True
    assert report.recommendation in ("full", "single")  # depends on whether a live agent is ready
    assert report.portions == ()  # no partitioning when it fits
    assert report.needed_human and report.free_human  # human-readable sizes present
    # collect_checks ran — at least the core deps are OK on this dev box
    assert report.checks_ok >= 1
    assert any("gateway" in line.lower() or "python" in line.lower() for line in report.check_lines)


def test_readiness_not_fits_yields_portions(tmp_path: Path, monkeypatch) -> None:
    ev = _evidence_with_zip(tmp_path, b"y" * 4096)
    # Force "won't fit": pretend almost no free disk so partition_plan engages.
    monkeypatch.setattr("siftmesh_core.evidence.space.free_bytes", lambda _p: 16)
    report = build_readiness(ev, run_location=tmp_path, settings=load_settings())
    assert report.fits is False
    assert report.recommendation == "portions"
    assert len(report.portions) >= 1  # the run-in-portions plan is offered


def test_check_lines_put_failures_first(tmp_path: Path) -> None:
    ev = _evidence_with_zip(tmp_path, b"z" * 256)
    report = build_readiness(ev, run_location=tmp_path, settings=load_settings())
    # any fail/warn lines sort before ok lines
    statuses = [line.split()[0] for line in report.check_lines]
    rank = {"fail": 0, "warn": 1, "ok": 2}
    assert statuses == sorted(statuses, key=lambda s: rank.get(s, 3))
