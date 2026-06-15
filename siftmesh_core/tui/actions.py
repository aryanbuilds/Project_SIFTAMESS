"""Governed-call wrappers for the cockpit (Epic C full-console) - Textual-FREE, unit-testable.

These mirror the EXACT governed sequences the CLI uses (`cli.retry`, `cli._resolve_gate`) so the TUI
duplicates no orchestration logic - it just calls these from `@work` threads. Each returns a short
status string for the UI to `notify()`; none touches the terminal.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from siftmesh_core.config import SiftmeshSettings
from siftmesh_core.run_dir import RunPaths
from siftmesh_core.schemas.run import GateName, GateStatus, RunMode, RunState


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
                False, f"retry refused: decide={decision.action} - {decision.reason}"
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


def run_in_portions(
    case_dir: str,
    portion_plan: list[list[object]],
    evidence_root: str,
    *,
    settings: SiftmeshSettings,
    mode: RunMode = "auto",
    brief: str | None = None,
    objective: str | None = None,
    progress: Callable[[str], None] | None = None,
    on_run: Callable[[RunPaths], None] | None = None,
) -> ActionResult:
    """Low-disk path: run the evidence in portions, pruning between, then merge into one report.

    Each portion is curated (hardlinked subset) → init → driven to terminal → pruned. After all
    portions, the runs are merged (``merge_runs`` needs >=2; a single portion just returns its run).
    Each portion IS an independent resumable run (own run_state + persisted curated dir). Blocking -
    call from a @work thread. ``progress`` reports per-portion; ``on_run`` hands each run to the UI
    so the cockpit can attach its live poll.
    """
    from pathlib import Path

    from siftmesh_core.evidence.curate import curate_evidence
    from siftmesh_core.evidence.prune import PrunePolicyError, prune_run
    from siftmesh_core.evidence.space import human_bytes
    from siftmesh_core.reports.merge_report import merge_runs
    from siftmesh_core.tui import runner

    def _emit(msg: str) -> None:
        if progress is not None:
            progress(msg)

    ev_root = Path(evidence_root)
    source_runs: list[RunPaths] = []
    try:
        total = len(portion_plan)
        for n, portion in enumerate(portion_plan, start=1):
            abs_paths = [ev_root / str(getattr(item, "path", item)) for item in portion]
            curated = curate_evidence(abs_paths, Path(case_dir) / f"curated_p{n}")
            _emit(f"portion {n}/{total}: running ({len(abs_paths)} artifacts)…")
            run = runner.init_case_for_run(
                case_dir,
                str(curated),
                mode=mode,
                settings=settings,
                brief=brief,
                objective=objective,
            )
            if on_run is not None:
                on_run(run)
            runner.drive_engine(run, str(curated), mode=mode, settings=settings)
            source_runs.append(run)
            try:
                outcome = prune_run(run)
                _emit(f"portion {n}/{total} done · pruned {human_bytes(outcome.bytes_freed)}")
            except PrunePolicyError:
                _emit(f"portion {n}/{total} done (not pruned - run not terminal)")
        if len(source_runs) < 2:
            one = source_runs[0].run_id if source_runs else "-"
            return ActionResult(True, f"single portion complete: {one}")
        merged = merge_runs(case_dir, [r.root for r in source_runs], settings=settings)
    except Exception as exc:
        return ActionResult(False, f"portions run failed: {exc}")
    return ActionResult(True, f"merged {len(source_runs)} portions → {merged.run_id}")
