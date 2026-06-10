"""H4/H5 — caps stop the loop; approval gates block, approve continues, reject halts."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from siftmesh_core.config import load_settings
from siftmesh_core.orchestrator import workflow_runner
from siftmesh_core.orchestrator.decide import decide
from siftmesh_core.orchestrator.human_gate import set_gate
from siftmesh_core.orchestrator.ultraworker import RunDecision
from siftmesh_core.orchestrator.workflow_runner import run_engine
from siftmesh_core.run_dir import RunPaths

BuiltRun = Callable[..., tuple[RunPaths, Path]]


def _results(run: RunPaths) -> list[Path]:
    return list(run.results.glob("TASK-*.result.json"))


def test_per_task_attempt_cap_escalates() -> None:
    # the distinct per-task counter: attempts exhausted -> escalate, not retry (pure decide)
    assert decide("retry_required", attempt=1, max_attempts=2).action == "retry"
    assert decide("retry_required", attempt=2, max_attempts=2).action == "escalate"


def test_auto_mode_stops_at_max_iterations(
    built_run: BuiltRun, monkeypatch: pytest.MonkeyPatch
) -> None:
    run, evidence = built_run(mode="auto", max_iterations=1)
    # Force a perpetual retry to exercise the GLOBAL cap (engine-logic test; tools stay real).
    monkeypatch.setattr(
        workflow_runner,
        "aggregate_decision",
        lambda run, state, *, settings: RunDecision("retry", "forced", ("TASK-001",)),
    )
    state = run_engine(run, settings=load_settings(), evidence_root=evidence)
    assert state.iteration == 1  # exactly one retry loop, then the cap halts it
    assert not state.terminal
    assert state.state == "decide"
    assert state.blocked_gate == "retry"
    assert run.token_budget.is_file()  # H9 routing decision recorded on the retry


def test_guided_mode_requires_approval_at_plan_gate(built_run: BuiltRun) -> None:
    run, evidence = built_run(mode="auto_human_loop")
    state = run_engine(run, settings=load_settings(), evidence_root=evidence)
    assert state.blocked_gate == "plan"
    assert state.state == "dispatch"  # halted on entry to dispatch, before any agent ran
    assert not state.terminal
    assert not _results(run)


def test_approve_gates_runs_to_done(built_run: BuiltRun) -> None:
    run, evidence = built_run(mode="auto_human_loop")
    settings = load_settings()
    run_engine(run, settings=settings, evidence_root=evidence)  # halts at plan gate
    set_gate(run, "plan", "approved")
    state = run_engine(run, settings=settings, evidence_root=evidence)  # halts at report gate
    assert state.blocked_gate == "report"
    assert _results(run)  # dispatch ran after the plan approval
    set_gate(run, "report", "approved")
    final = run_engine(run, settings=settings, evidence_root=evidence)
    assert final.state == "done"
    assert final.terminal


def test_reject_plan_gate_halts(built_run: BuiltRun) -> None:
    run, evidence = built_run(mode="auto_human_loop")
    settings = load_settings()
    run_engine(run, settings=settings, evidence_root=evidence)  # halts at plan gate
    set_gate(run, "plan", "rejected")
    final = run_engine(run, settings=settings, evidence_root=evidence)
    assert final.terminal
    assert not _results(run)  # rejected before any dispatch
