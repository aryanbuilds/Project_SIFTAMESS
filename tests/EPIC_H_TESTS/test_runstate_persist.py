"""H1 - RunState atomic persistence: round-trip, no temp leak, crash-safe replace."""

from __future__ import annotations

from pathlib import Path

from siftmesh_core.orchestrator.run_state_store import (
    read_run_state,
    run_state_exists,
    write_run_state,
)
from siftmesh_core.run_dir import RunPaths, new_run_dir
from siftmesh_core.schemas.run import PerTaskState, RunState


def _run(tmp_path: Path) -> RunPaths:
    return new_run_dir(base=tmp_path / "case_runs")


def test_runstate_roundtrip(tmp_path: Path) -> None:
    run = _run(tmp_path)
    state = RunState(
        run_id=run.run_id,
        state="decide",
        mode="auto",
        iteration=2,
        max_iterations=3,
        per_task={"TASK-001": PerTaskState(attempt=2, max_attempts=2, status="success")},
        gates={"plan": "approved"},
    )
    written = write_run_state(run, state)
    assert run_state_exists(run)
    # byte-identical round-trip (updated_utc is stamped on write and persisted)
    assert read_run_state(run).model_dump_json() == written.model_dump_json()


def test_write_leaves_no_temp_file(tmp_path: Path) -> None:
    run = _run(tmp_path)
    write_run_state(run, RunState(run_id=run.run_id))
    write_run_state(run, RunState(run_id=run.run_id, state="plan"))  # overwrite
    leftovers = list(run.root.glob(".run_state-*.tmp"))
    assert leftovers == []
    assert read_run_state(run).state == "plan"  # last write wins, always valid


def test_read_missing_raises(tmp_path: Path) -> None:
    run = _run(tmp_path)
    assert not run_state_exists(run)
    try:
        read_run_state(run)
    except FileNotFoundError:
        return
    raise AssertionError("expected FileNotFoundError for a missing run_state.json")
