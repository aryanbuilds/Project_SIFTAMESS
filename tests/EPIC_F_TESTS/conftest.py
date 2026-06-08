"""Epic F shared fixtures — a fully-planned run over REAL committed fixtures.

The deterministic executor runs the real Epic-D tools, so these tests need real
artifact bytes (unlike Epic E, which is metadata-only). Fixtures are the public
upstream samples in ``tests/fixtures/forensic/`` — never SANS evidence. No keys,
no live agent.
"""

from __future__ import annotations

import lzma
import shutil
from collections.abc import Callable
from pathlib import Path

import pytest
from siftmesh_core.config import load_settings
from siftmesh_core.evidence.manifest import build_manifest_from_dir, write_manifest
from siftmesh_core.evidence.readonly import write_readonly_record
from siftmesh_core.orchestrator.planner import generate_plan
from siftmesh_core.run_dir import RunPaths, new_run_dir

_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "forensic"


def _build_evidence(evidence: Path) -> None:
    evidence.mkdir(parents=True, exist_ok=True)
    shutil.copy(_FIXTURES / "security_short.evtx", evidence / "Security.evtx")
    shutil.copy(_FIXTURES / "prefetch_vista_cmd.pf", evidence / "CMD.EXE-89305D47.pf")
    shutil.copy(_FIXTURES / "mft_entry_single", evidence / "$MFT")
    (evidence / "NTUSER.DAT").write_bytes(
        lzma.decompress((_FIXTURES / "ntuser.dat.xz").read_bytes())
    )


RealCase = Callable[..., tuple[RunPaths, Path]]


@pytest.fixture
def real_case(tmp_path: Path) -> RealCase:
    """Factory: build a planned run over the real fixtures; return (run, evidence_root)."""

    def _make(*, review_only: bool = False) -> tuple[RunPaths, Path]:
        evidence = tmp_path / "evidence"
        _build_evidence(evidence)
        run = new_run_dir(base=tmp_path / "case_runs")
        manifest = build_manifest_from_dir(evidence, case_id="case01", run_id=run.run_id)
        write_manifest(manifest, run.root, evidence_root=evidence)
        write_readonly_record(evidence, run.root, file_count=len(manifest.files))
        generate_plan(run, settings=load_settings(), review_only=review_only)
        return run, evidence

    return _make
