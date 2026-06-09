"""resolved_source: two trusted roots (evidence + run) for derived artifacts; traversal stays shut.

Regression for the live-agent bug where derived artifacts (carved under run_root/evidence/extracted)
could not be read because the server scopes evidence_root to the raw vault only.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from siftmesh_core.mcp_gateway.tools._common import resolved_source


def _seed(root: Path, rel: str, data: bytes = b"real artifact bytes") -> None:
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)


def test_resolves_under_evidence_root(tmp_path: Path) -> None:
    ev = tmp_path / "evidence"
    _seed(ev, "Security.evtx")
    path, sha = resolved_source(ev, "Security.evtx")
    assert path == (ev / "Security.evtx").resolve()
    assert len(sha) == 64


def test_resolves_derived_under_run_root(tmp_path: Path) -> None:
    # The derived artifact lives under run_root, NOT under the (raw-vault) evidence_root.
    ev = tmp_path / "evidence"
    ev.mkdir()
    run = tmp_path / "case_runs" / "RUN-x"
    _seed(run, "evidence/extracted/Microsoft-Windows-PowerShell%4Operational.evtx")
    rel = "evidence/extracted/Microsoft-Windows-PowerShell%4Operational.evtx"
    # without run_root the derived read fails closed...
    with pytest.raises(FileNotFoundError):
        resolved_source(ev, rel)
    # ...with run_root it resolves under the run tree
    path, sha = resolved_source(ev, rel, run_root=run)
    assert path == (run / rel).resolve()
    assert len(sha) == 64


def test_traversal_outside_both_roots_rejected(tmp_path: Path) -> None:
    ev = tmp_path / "evidence"
    ev.mkdir()
    run = tmp_path / "case_runs" / "RUN-x"
    run.mkdir(parents=True)
    (tmp_path / "secret.txt").write_bytes(b"do not read")
    with pytest.raises(ValueError, match="escapes evidence root"):
        resolved_source(ev, "../../secret.txt", run_root=run)


def test_missing_file_under_valid_root_is_not_found(tmp_path: Path) -> None:
    ev = tmp_path / "evidence"
    ev.mkdir()
    run = tmp_path / "run"
    run.mkdir()
    with pytest.raises(FileNotFoundError):
        resolved_source(ev, "nope.evtx", run_root=run)


def test_evidence_root_wins_when_both_contain(tmp_path: Path) -> None:
    # Same relative path present under both roots -> the evidence root (first/trusted) is used.
    ev = tmp_path / "evidence"
    run = tmp_path / "run"
    _seed(ev, "dup.bin", b"evidence-copy")
    _seed(run, "dup.bin", b"run-copy")
    path, _ = resolved_source(ev, "dup.bin", run_root=run)
    assert path == (ev / "dup.bin").resolve()
