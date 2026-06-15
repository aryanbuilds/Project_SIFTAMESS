"""Approval-gate helpers (H5) - record a human approve/reject on a run.

The engine (``workflow_runner``) halts on a pending meaningful gate in guided mode and persists
``RunState.blocked_gate``. The ``approve``/``reject`` CLI commands call :func:`set_gate` to record
the human decision into the durable RunState; ``approve`` then resumes the engine, ``reject`` aborts
the run on the next entry to that gate.
"""

from __future__ import annotations

from siftmesh_core.orchestrator.run_state_store import read_run_state, write_run_state
from siftmesh_core.run_dir import RunPaths
from siftmesh_core.schemas.run import GateName, GateStatus, RunState

GATES: tuple[GateName, ...] = ("plan", "dispatch", "retry", "report")


def set_gate(run: RunPaths, gate: GateName, status: GateStatus) -> RunState:
    """Persist a gate decision into the run's durable state; return the new state."""
    state = read_run_state(run)
    gates = dict(state.gates)
    gates[gate] = status
    return write_run_state(run, state.model_copy(update={"gates": gates}))
