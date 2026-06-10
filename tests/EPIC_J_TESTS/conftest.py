"""Epic J shared fixtures — real runs to render reports from (no keys, no live agent).

``dispatched_run`` is a real planned + dispatched + critiqued run over the committed public fixtures
(real Epic-D tools → real claims/tool_calls/verdicts), so reports render from a genuine ledger set.
``planned_run`` is plan-only (no execution) for the empty/halted edge cases. The builders are
duplicated from EPIC_F/EPIC_G (cross-dir conftest import is disallowed by the conventions).
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
from siftmesh_core.orchestrator.critic import critique_run
from siftmesh_core.orchestrator.planner import generate_plan
from siftmesh_core.orchestrator.scheduler import dispatch_run
from siftmesh_core.run_dir import RunPaths, new_run_dir

_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "forensic"

Case = Callable[..., tuple[RunPaths, Path]]


def _build_evidence(evidence: Path) -> None:
    evidence.mkdir(parents=True, exist_ok=True)
    shutil.copy(_FIXTURES / "security_short.evtx", evidence / "Security.evtx")
    shutil.copy(_FIXTURES / "prefetch_vista_cmd.pf", evidence / "CMD.EXE-89305D47.pf")
    (evidence / "NTUSER.DAT").write_bytes(
        lzma.decompress((_FIXTURES / "ntuser.dat.xz").read_bytes())
    )


def _seal(tmp_path: Path) -> tuple[RunPaths, Path]:
    evidence = tmp_path / "evidence"
    _build_evidence(evidence)
    run = new_run_dir(base=tmp_path / "case_runs")
    manifest = build_manifest_from_dir(evidence, case_id="case01", run_id=run.run_id)
    write_manifest(manifest, run.root, evidence_root=evidence)
    write_readonly_record(evidence, run.root, file_count=len(manifest.files))
    generate_plan(run, settings=load_settings())
    return run, evidence


@pytest.fixture
def dispatched_run(tmp_path: Path) -> Case:
    """Factory: a real planned + dispatched + critiqued run → (run, evidence_root)."""

    def _make(*, critique: bool = True) -> tuple[RunPaths, Path]:
        run, evidence = _seal(tmp_path)
        dispatch_run(run, settings=load_settings())
        if critique:
            critique_run(run, settings=load_settings(), evidence_root=evidence)
        return run, evidence

    return _make


@pytest.fixture
def planned_run(tmp_path: Path) -> Case:
    """Factory: a sealed + planned run with NO execution (empty ledgers) → (run, evidence_root)."""

    def _make() -> tuple[RunPaths, Path]:
        return _seal(tmp_path)

    return _make
