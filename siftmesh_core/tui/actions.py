"""Governed-call wrappers for the cockpit (Epic C full-console) — Textual-FREE, unit-testable.

These mirror the EXACT governed sequences the CLI uses (`cli.retry`, `cli._resolve_gate`) so the TUI
duplicates no orchestration logic — it just calls these from `@work` threads. Each returns a short
status string for the UI to `notify()`; none touches the terminal.
"""

from __future__ import annotations

from dataclasses import dataclass

from siftmesh_core.config import SiftmeshSettings
from siftmesh_core.run_dir import RunPaths
from siftmesh_core.schemas.run import GateName, GateStatus, RunState


@dataclass(frozen=True)
class ActionResult:
    """Outcome of a governed cockpit action."""

    ok: bool
    message: str
    state: RunState | None = None


def retry_task(run: RunPaths, task_id: str, *, settings: SiftmeshSettings) -> ActionResult:
    """Re-critique one task; if DECIDE says retry, tighten + re-dispatch (mirrors ``cli.retry``)."""
    from siftmesh_core.orchestrator.critic import critique_run, write_retry
    from siftmesh_core.orchestrator.decide import decide
    from siftmesh_core.orchestrator.scheduler import dispatch_run
    from siftmesh_core.schemas.task import TaskContract
    from siftmesh_core.schemas.task_result import TaskResult
    from siftmesh_core.schemas.yaml_io import read_yaml_model

    result_path = run.result_path(task_id)
    if not result_path.is_file():
        return ActionResult(False, f"no result for {task_id}")
    try:
        result = TaskResult.model_validate_json(result_path.read_text(encoding="utf-8"))
        contract = read_yaml_model(TaskContract, run.tasks / f"{task_id}.yaml")
        verdicts = {
            v.task_id: v for v in critique_run(run, settings=settings, generate_followups=False)
        }
        verdict = verdicts.get(task_id)
        if verdict is None:
            return ActionResult(False, f"no critic verdict for {task_id}")
        decision = decide(
            verdict.verdict,
            attempt=result.attempt,
            max_attempts=contract.retry_policy.max_attempts,
            max_iterations=settings.caps.max_iterations,
        )
        if decision.action != "retry":
            return ActionResult(
                False, f"retry refused: decide={decision.action} — {decision.reason}"
            )
        write_retry(run, contract, from_attempt=result.attempt, cause=verdict.verdict)
        refs = dispatch_run(
            run,
            settings=settings,
            task_id=task_id,
            attempt=result.attempt + 1,
            critic_feedback=tuple(verdict.reasons),
        )
    except Exception as exc:  # surface, never crash the cockpit
        return ActionResult(False, f"retry failed: {exc}")
    return ActionResult(True, f"retry {task_id} attempt {result.attempt + 1} -> {refs[0].status}")


def resolve_gate(
    run: RunPaths, gate: GateName, *, approve: bool, settings: SiftmeshSettings
) -> ActionResult:
    """Record an approve/reject gate decision; on approve resume the engine (mirrors the CLI)."""
    from siftmesh_core.orchestrator.human_gate import set_gate
    from siftmesh_core.orchestrator.workflow_runner import run_engine

    status: GateStatus = "approved" if approve else "rejected"
    try:
        state = set_gate(run, gate, status)
        if approve:
            state = run_engine(run, settings=settings, single_step=(state.mode == "manual"))
    except Exception as exc:
        return ActionResult(False, f"{'approve' if approve else 'reject'} failed: {exc}")
    return ActionResult(True, f"{'approved' if approve else 'rejected'} gate {gate}", state)
