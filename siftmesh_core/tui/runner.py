"""Drive a full run for the TUI launcher (Epic O).

A thin MIRROR of the core of the ``siftmesh run`` CLI command (cli.run) — init the case, write the
initial RunState with the chosen mode/caps, then drive the deterministic engine. Kept here so the
cockpit's background worker reuses the EXACT governed path (no parallel orchestration logic). If
cli.run's core changes, update both. The space pre-flight is intentionally omitted (the TUI launcher
exposes evidence size separately); everything else matches.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from siftmesh_core.config import SiftmeshSettings
from siftmesh_core.evidence.vault import init_case as vault_init_case
from siftmesh_core.orchestrator.run_state_store import write_run_state
from siftmesh_core.orchestrator.workflow_runner import run_engine
from siftmesh_core.run_dir import RunPaths
from siftmesh_core.schemas.run import RunMode, RunState


def init_case_for_run(
    case_dir: str,
    evidence: str,
    *,
    mode: RunMode,
    settings: SiftmeshSettings,
    max_iterations: int | None = None,
    brief: str | None = None,
    objective: str | None = None,
) -> RunPaths:
    """Create the run dir + seal evidence + write the initial RunState; return its RunPaths.

    Synchronous (hashes evidence) but quick for demo-scale data; the cockpit calls this first so it
    knows the run dir, then drives the engine in a worker. Mirrors cli.run init.
    """
    run = vault_init_case(
        case_dir, evidence, show_progress=False, brief_path=brief, objective_text=objective
    )
    state = RunState(
        run_id=run.run_id,
        mode=mode,
        max_iterations=max_iterations or settings.caps.max_iterations,
    )
    write_run_state(run, state)
    return run


def drive_engine(
    run: RunPaths,
    evidence: str,
    *,
    mode: RunMode,
    settings: SiftmeshSettings,
    on_error: Callable[[str], None] | None = None,
) -> None:
    """Run the deterministic engine to completion/halt (blocking — call from a worker thread)."""
    try:
        run_engine(
            run,
            settings=settings,
            evidence_root=Path(evidence),
            single_step=(mode == "manual"),
        )
    except Exception as exc:  # surface to the UI; the run dir holds the real state
        if on_error is not None:
            on_error(str(exc))
