"""Epic G shared fixtures — a dispatched run over REAL fixtures, ready to critique.

Builds a planned + dispatched run (real Epic-D tools over the committed public
fixtures), so the critic has a real manifest + tool_calls.jsonl + claim ledger to
validate against. Crafted TaskResults (for rejection/retry/injection tests) are
written into this real run. No keys, no live agent — governance tests only.
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
from siftmesh_core.orchestrator.scheduler import dispatch_run
from siftmesh_core.run_dir import RunPaths, new_run_dir

_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "forensic"


def _build_evidence(evidence: Path) -> None:
    evidence.mkdir(parents=True, exist_ok=True)
    shutil.copy(_FIXTURES / "security_short.evtx", evidence / "Security.evtx")
    shutil.copy(_FIXTURES / "prefetch_vista_cmd.pf", evidence / "CMD.EXE-89305D47.pf")
    (evidence / "NTUSER.DAT").write_bytes(
        lzma.decompress((_FIXTURES / "ntuser.dat.xz").read_bytes())
    )


DispatchedCase = Callable[..., tuple[RunPaths, Path]]


@pytest.fixture
def dispatched_case(tmp_path: Path) -> DispatchedCase:
    """Factory: a planned + dispatched run over real fixtures → (run, evidence_root)."""

    def _make(*, dispatch: bool = True) -> tuple[RunPaths, Path]:
        evidence = tmp_path / "evidence"
        _build_evidence(evidence)
        run = new_run_dir(base=tmp_path / "case_runs")
        manifest = build_manifest_from_dir(evidence, case_id="case01", run_id=run.run_id)
        write_manifest(manifest, run.root, evidence_root=evidence)
        write_readonly_record(evidence, run.root, file_count=len(manifest.files))
        generate_plan(run, settings=load_settings())
        if dispatch:
            dispatch_run(run, settings=load_settings())
        return run, evidence

    return _make
