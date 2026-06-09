"""H3/H6/H7/H8 — the engine drives the real pipeline to DONE, resumes, and audits."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from siftmesh_core.config import load_settings
from siftmesh_core.orchestrator.run_state_store import run_state_exists
from siftmesh_core.orchestrator.workflow_runner import run_engine
from siftmesh_core.run_dir import RunPaths

BuiltRun = Callable[..., tuple[RunPaths, Path]]


def _results(run: RunPaths) -> list[Path]:
    return list(run.results.glob("TASK-*.result.json"))


def test_auto_run_reaches_done(built_run: BuiltRun) -> None:
    run, evidence = built_run(mode="auto")
    state = run_engine(run, settings=load_settings(), evidence_root=evidence)
    assert state.state == "done"
    assert state.terminal
    assert _results(run)  # real tools ran
    assert run.claim_ledger.read_text(encoding="utf-8").strip()  # claims written
    assert run_state_exists(run)
    events = run.orchestration_events.read_text(encoding="utf-8")
    assert "transition" in events and "run_complete" in events  # H8


def test_review_only_stops_after_plan(built_run: BuiltRun) -> None:
    run, evidence = built_run(mode="review_only")
    state = run_engine(run, settings=load_settings(), evidence_root=evidence)
    assert state.state == "done"
    assert state.terminal
    assert list(run.tasks.glob("TASK-*.yaml"))  # plan ran
    assert not _results(run)  # dispatch was unreachable


def test_resume_from_midrun_reaches_done(built_run: BuiltRun) -> None:
    run, evidence = built_run(mode="auto")
    settings = load_settings()
    state = None
    for _ in range(5):  # single-step: init→cev→dc→plan→dispatch→collect
        state = run_engine(run, settings=settings, evidence_root=evidence, single_step=True)
        if state.terminal:
            break
    assert state is not None and not state.terminal
    assert state.state in ("dispatch", "collect", "critique")  # interrupted mid-run
    final = run_engine(run, settings=settings, evidence_root=evidence)  # resume to completion
    assert final.state == "done"
    assert final.terminal


def test_manual_artifacts_equal_auto_artifacts(built_run: BuiltRun) -> None:
    settings = load_settings()
    run_auto, evidence = built_run(mode="auto")
    run_manual, _ = built_run(mode="manual")
    run_engine(run_auto, settings=settings, evidence_root=evidence)
    state = None
    for _ in range(20):  # one engine, single-stepped to completion
        state = run_engine(run_manual, settings=settings, evidence_root=evidence, single_step=True)
        if state.terminal:
            break
    assert state is not None and state.state == "done"
    auto_results = sorted(p.name for p in _results(run_auto))
    manual_results = sorted(p.name for p in _results(run_manual))
    assert auto_results == manual_results and auto_results
    auto_claims = run_auto.claim_ledger.read_text(encoding="utf-8").strip().splitlines()
    manual_claims = run_manual.claim_ledger.read_text(encoding="utf-8").strip().splitlines()
    assert len(auto_claims) == len(manual_claims)
