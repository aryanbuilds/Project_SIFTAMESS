"""Cockpit governed-call wrappers (Epic C full-console) — Textual-FREE, no terminal.

`tui/actions.py` must mirror the CLI's governed sequences exactly: retry only re-dispatches when
DECIDE says retry; resolve_gate writes the gate via the governed `set_gate`. Tested headless over
the golden run (no keys, no live agent).
"""

from __future__ import annotations

import shutil
from pathlib import Path

from siftmesh_core.config import load_settings
from siftmesh_core.orchestrator.run_state_store import read_run_state, run_state_exists
from siftmesh_core.run_dir import RunPaths
from siftmesh_core.tui import actions

GOLDEN = Path(__file__).resolve().parents[1] / "golden" / "recorded_run" / "RUN-GOLDEN"


def _golden_copy(tmp_path: Path) -> RunPaths:
    dst = tmp_path / "RUN-GOLDEN"
    shutil.copytree(GOLDEN, dst)
    return RunPaths(root=dst)


def test_retry_refuses_when_decide_not_retry(tmp_path: Path) -> None:
    # Golden tasks are all accepted → decide != retry → retry must refuse (no re-dispatch).
    run = _golden_copy(tmp_path)
    res = actions.retry_task(run, "TASK-001", settings=load_settings())
    assert res.ok is False
    assert "refused" in res.message or "no result" in res.message


def test_retry_unknown_task_is_clean_error(tmp_path: Path) -> None:
    run = _golden_copy(tmp_path)
    res = actions.retry_task(run, "TASK-999", settings=load_settings())
    assert res.ok is False  # no crash, honest message


def test_resolve_gate_writes_gate(tmp_path: Path) -> None:
    run = _golden_copy(tmp_path)
    if not run_state_exists(run):  # golden may have no run_state; reject still records the gate
        from siftmesh_core.orchestrator.run_state_store import write_run_state
        from siftmesh_core.schemas.run import RunState

        write_run_state(run, RunState(run_id=run.run_id, mode="auto_human_loop", state="plan"))
    res = actions.resolve_gate(run, "plan", approve=False, settings=load_settings())
    assert res.ok is True
    assert read_run_state(run).gates.get("plan") == "rejected"  # governed set_gate happened
