"""Shared pytest fixtures - the ONE real-fixture run factory + CLI harness (Epic M1).

``make_real_run`` is the consolidated builder every per-epic conftest delegates to
(previously duplicated ~5x across EPIC_F/G/H/J/L): real committed forensic fixtures →
manifest + readonly record → optional plan / dispatch / critique. Real tools, real
output, no keys, no live agent, never SANS evidence (CLAUDE §2B).

The Hypothesis "siftmesh" profile pins property tests deterministic (replayable suite).
"""

from __future__ import annotations

import lzma
import shutil
from collections.abc import Callable
from pathlib import Path

import pytest
import typer
from hypothesis import settings as hypothesis_settings
from siftmesh_core.cli import app
from siftmesh_core.config import load_settings
from siftmesh_core.evidence.manifest import build_manifest_from_dir, write_manifest
from siftmesh_core.evidence.readonly import write_readonly_record
from siftmesh_core.orchestrator.critic import critique_run
from siftmesh_core.orchestrator.planner import generate_plan
from siftmesh_core.orchestrator.scheduler import dispatch_run
from siftmesh_core.run_dir import RunPaths, new_run_dir
from typer.testing import CliRunner

FORENSIC_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "forensic"

# Deterministic property tests everywhere (no env juggling; the suite is replayable).
hypothesis_settings.register_profile("siftmesh", derandomize=True)
hypothesis_settings.load_profile("siftmesh")

BuildEvidence = Callable[..., None]
MakeRealRun = Callable[..., tuple[RunPaths, Path]]


@pytest.fixture
def runner() -> CliRunner:
    # Do NOT pass mix_stderr= - removed in Typer 0.16+ (Click 8.2 alignment).
    return CliRunner()


@pytest.fixture
def cli_app() -> typer.Typer:
    return app


@pytest.fixture
def build_evidence() -> BuildEvidence:
    """Callable: lay the real committed forensic fixtures down as an evidence tree."""

    def _build(evidence: Path, *, with_mft: bool = False) -> None:
        evidence.mkdir(parents=True, exist_ok=True)
        shutil.copy(FORENSIC_FIXTURES / "security_short.evtx", evidence / "Security.evtx")
        shutil.copy(FORENSIC_FIXTURES / "prefetch_vista_cmd.pf", evidence / "CMD.EXE-89305D47.pf")
        (evidence / "NTUSER.DAT").write_bytes(
            lzma.decompress((FORENSIC_FIXTURES / "ntuser.dat.xz").read_bytes())
        )
        if with_mft:
            shutil.copy(FORENSIC_FIXTURES / "mft_entry_single", evidence / "$MFT")

    return _build


@pytest.fixture
def make_real_run(tmp_path: Path, build_evidence: BuildEvidence) -> MakeRealRun:
    """Factory: a real run over real fixtures -> (run, evidence_root).

    Stages are opt-in so one factory serves every epic: ``plan`` (default) ->
    ``dispatch`` (real Epic-D tools execute) -> ``critique`` (verdicts + promoted
    claims). ``review_only`` plans without actionable dispatch; ``with_mft`` adds
    the $MFT fixture (timeline lane).
    """

    def _make(
        *,
        plan: bool = True,
        review_only: bool = False,
        dispatch: bool = False,
        critique: bool = False,
        with_mft: bool = False,
    ) -> tuple[RunPaths, Path]:
        evidence = tmp_path / "evidence"
        build_evidence(evidence, with_mft=with_mft)
        run = new_run_dir(base=tmp_path / "case_runs")
        manifest = build_manifest_from_dir(evidence, case_id="case01", run_id=run.run_id)
        write_manifest(manifest, run.root, evidence_root=evidence)
        write_readonly_record(evidence, run.root, file_count=len(manifest.files))
        if plan:
            generate_plan(run, settings=load_settings(), review_only=review_only)
        if dispatch:
            dispatch_run(run, settings=load_settings())
        if critique:
            critique_run(run, settings=load_settings(), evidence_root=evidence)
        return run, evidence

    return _make
