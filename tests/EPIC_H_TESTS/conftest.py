"""Epic H shared fixtures — an init-ready run over REAL fixtures, for the engine.

Builds a run dir with a real evidence manifest + readonly-mounts record + an initial RunState,
so ``run_engine`` can drive the full state machine (create_evidence_vault → plan → dispatch →
collect → critique → decide → report → done) over the committed public fixtures. No keys, no
live agent — the deterministic floor runs the real Epic-D tools.
"""

from __future__ import annotations

import lzma
import shutil
from collections.abc import Callable
from pathlib import Path

import pytest
from siftmesh_core.evidence.manifest import build_manifest_from_dir, write_manifest
from siftmesh_core.evidence.readonly import write_readonly_record
from siftmesh_core.orchestrator.run_state_store import write_run_state
from siftmesh_core.run_dir import RunPaths, new_run_dir
from siftmesh_core.schemas.run import RunMode, RunState

_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "forensic"

# Factory: (mode, max_iterations) -> a planned-ready run + its evidence root.
BuiltRun = Callable[..., tuple[RunPaths, Path]]


def _build_evidence(evidence: Path) -> None:
    evidence.mkdir(parents=True, exist_ok=True)
    shutil.copy(_FIXTURES / "security_short.evtx", evidence / "Security.evtx")
    shutil.copy(_FIXTURES / "prefetch_vista_cmd.pf", evidence / "CMD.EXE-89305D47.pf")
    (evidence / "NTUSER.DAT").write_bytes(
        lzma.decompress((_FIXTURES / "ntuser.dat.xz").read_bytes())
    )


@pytest.fixture
def built_run(tmp_path: Path) -> BuiltRun:
    """Factory: an init-ready run (manifest + readonly + RunState) → (run, evidence_root)."""

    def _make(*, mode: RunMode = "auto", max_iterations: int = 3) -> tuple[RunPaths, Path]:
        evidence = tmp_path / "evidence"
        _build_evidence(evidence)
        run = new_run_dir(base=tmp_path / "case_runs")
        manifest = build_manifest_from_dir(evidence, case_id="case01", run_id=run.run_id)
        write_manifest(manifest, run.root, evidence_root=evidence)
        write_readonly_record(evidence, run.root, file_count=len(manifest.files))
        write_run_state(run, RunState(run_id=run.run_id, mode=mode, max_iterations=max_iterations))
        return run, evidence

    return _make


@pytest.fixture
def evidence_dir(tmp_path: Path) -> Path:
    """A read-only evidence dir of real fixtures, for `siftmesh run` CLI tests (init-case)."""
    evidence = tmp_path / "evidence"
    _build_evidence(evidence)
    return evidence
