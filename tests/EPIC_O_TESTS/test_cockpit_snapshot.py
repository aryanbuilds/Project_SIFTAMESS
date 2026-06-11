"""Epic O — the cockpit data layer (Textual-free; deterministic, against the golden run)."""

from __future__ import annotations

import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path

from siftmesh_core.run_dir import RunPaths, new_run_dir
from siftmesh_core.schemas.run import PerTaskState, RunState
from siftmesh_core.tui.snapshot import STAGE_ORDER, build_snapshot

GOLDEN = Path(__file__).resolve().parents[1] / "golden" / "recorded_run" / "RUN-GOLDEN"
_NOW = datetime(2030, 1, 1, tzinfo=UTC)


def test_golden_ledger_snapshot_renders_without_run_state() -> None:
    # The golden run has full ledgers but NO run_state.json — the snapshot must still render the
    # tasks/claims/agents/events from the ledgers (run_state is optional).
    snap = build_snapshot(RunPaths(root=GOLDEN), now=_NOW)
    assert snap.exists is True
    assert snap.tasks_total == 4
    assert snap.tasks_done == 4  # all dispatched (agent_calls present)
    assert snap.claim_counts == {"confirmed": 5, "inferred": 2, "contradicted": 0, "unsupported": 0}
    assert snap.verdict_tally == {"accepted": 4}
    assert len(snap.agent_sessions) == 4
    assert len(snap.events) == 10
    assert snap.current_agent == "deterministic_executor"
    families = {t.family for t in snap.tasks}
    assert {"prefetch", "registry_hive", "evtx_security", "timeline"} <= families
    # every task row carries its promoted-claim count + accepted verdict
    assert all(t.verdict == "accepted" for t in snap.tasks)
    assert sum(t.claims for t in snap.tasks) == 7  # 5 confirmed + 2 inferred


def test_empty_run_with_tmp(tmp_path: Path) -> None:
    run = new_run_dir(base=tmp_path)
    snap = build_snapshot(run, now=_NOW)
    assert snap.exists is False
    assert snap.tasks_total == 0
    assert snap.stage == "init"
    assert all(c.state == "pending" for c in snap.pipeline)


def _golden_copy(tmp_path: Path) -> RunPaths:
    dest = tmp_path / "RUN-LIVE"
    shutil.copytree(GOLDEN, dest)
    return RunPaths(root=dest)


def test_state_drives_stage_mode_and_pipeline(tmp_path: Path) -> None:
    # With run_state.json present, stage/mode/iteration/pipeline come from it (the live path).
    run = _golden_copy(tmp_path)
    entered = _NOW - timedelta(seconds=30)
    state = RunState(
        run_id="RUN-LIVE",
        state="critique",
        mode="auto",
        iteration=1,
        max_iterations=3,
        per_task={"TASK-001": PerTaskState(attempt=2, max_attempts=2, status="retry_required")},
        updated_utc=entered,
    )
    run.run_state.write_text(state.model_dump_json(indent=2) + "\n", encoding="utf-8")

    snap = build_snapshot(run, now=_NOW)
    assert snap.stage == "critique"
    assert snap.mode == "auto"
    assert snap.iteration == 1 and snap.max_iterations == 3
    assert round(snap.stage_elapsed_s) == 30  # now - updated_utc
    assert snap.total_elapsed_s > 0
    # pipeline: everything before critique done, critique current, after pending
    cur = STAGE_ORDER.index("critique")
    states = {c.name: c.state for c in snap.pipeline}
    assert states["plan"] == "done" and states["dispatch"] == "done"
    assert states["critique"] == "current"
    assert states[STAGE_ORDER[cur + 1]] == "pending"
    # per_task status overrides the dispatched default
    t1 = next(t for t in snap.tasks if t.task_id == "TASK-001")
    assert t1.status == "retry_required" and t1.attempt == 2


def test_timers_freeze_when_terminal(tmp_path: Path) -> None:
    # A terminal run freezes total_elapsed at the last event time (independent of `now`).
    run = _golden_copy(tmp_path)
    state = RunState(run_id="RUN-LIVE", state="done", mode="auto", terminal=True, updated_utc=_NOW)
    run.run_state.write_text(state.model_dump_json(indent=2) + "\n", encoding="utf-8")
    early = build_snapshot(run, now=_NOW)
    late = build_snapshot(run, now=_NOW + timedelta(hours=5))
    assert early.total_elapsed_s == late.total_elapsed_s  # frozen at last event, not `now`
    assert all(c.state == "done" for c in late.pipeline)
