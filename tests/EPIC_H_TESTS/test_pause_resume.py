"""Cooperative pause hook (TUI) - run_engine should_stop stops at a safe checkpoint, then resumes.

The pause must be graceful (state durable + consistent) and resumable to the SAME artifacts as an
uninterrupted run. Default (no should_stop) is byte-identical to before - guarded by the rest of
test_runner_engine.py.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from siftmesh_core.config import load_settings
from siftmesh_core.orchestrator.run_state_store import read_run_state
from siftmesh_core.orchestrator.workflow_runner import run_engine
from siftmesh_core.run_dir import RunPaths

BuiltRun = Callable[..., tuple[RunPaths, Path]]


def _results(run: RunPaths) -> set[str]:
    return {p.name for p in run.results.glob("TASK-*.result.json")}


def test_pause_then_resume_reaches_done_with_paused_event(built_run: BuiltRun) -> None:
    run, evidence = built_run(mode="auto")
    settings = load_settings()

    # should_stop True → stop at the first safe checkpoint (after one transition), state consistent.
    paused = run_engine(run, settings=settings, evidence_root=evidence, should_stop=lambda: True)
    assert not paused.terminal  # halted early, not finished
    on_disk = read_run_state(run)
    assert on_disk.state == paused.state and not on_disk.terminal  # persisted + consistent
    assert "paused" in run.orchestration_events.read_text(encoding="utf-8")

    # Resume (no stop) → drive to done.
    final = run_engine(run, settings=settings, evidence_root=evidence)
    assert final.terminal
    assert _results(run)  # real tools ran


def test_paused_resume_equals_uninterrupted(built_run: BuiltRun) -> None:
    settings = load_settings()
    # Uninterrupted reference run.
    ref, evidence = built_run(mode="auto")
    run_engine(ref, settings=settings, evidence_root=evidence)

    # A run paused once mid-flight, then resumed.
    paused, ev2 = built_run(mode="auto")
    run_engine(paused, settings=settings, evidence_root=ev2, should_stop=lambda: True)
    final = run_engine(paused, settings=settings, evidence_root=ev2)

    assert final.terminal
    # Same set of task results + same number of promoted claims (artifacts equivalent).
    assert _results(paused) == _results(ref)
    assert len(paused.claim_ledger.read_text().splitlines()) == len(
        ref.claim_ledger.read_text().splitlines()
    )


def test_default_no_should_stop_runs_to_done(built_run: BuiltRun) -> None:
    run, evidence = built_run(mode="auto")
    state = run_engine(run, settings=load_settings(), evidence_root=evidence)  # no should_stop
    assert state.terminal  # default path unchanged
