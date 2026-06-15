"""Run-level decision aggregation (H3) - the Ultraworker's per-iteration choice.

After CRITIQUE the run has one persisted ``CriticVerdict`` per task. ``aggregate_decision`` maps
each verdict through the pure :func:`decide` truth table and folds the per-task actions into one
run-level action by worst-case precedence: ``human_review > escalate > retry > follow_up > done``.
Verdicts are read from the persisted ledger (not memory) so the choice is identical on a resumed
run. The heavy logic stays in pure ``decide``; this only aggregates.
"""

from __future__ import annotations

from dataclasses import dataclass

from siftmesh_core.config import SiftmeshSettings
from siftmesh_core.ledgers.critic_verdicts import read_critic_verdicts
from siftmesh_core.orchestrator.decide import decide
from siftmesh_core.run_dir import RunPaths
from siftmesh_core.schemas.audit import CriticVerdict
from siftmesh_core.schemas.decision import DecisionAction
from siftmesh_core.schemas.run import PerTaskState, RunState

_RESULT_SUFFIX = ".result.json"


@dataclass(frozen=True)
class RunDecision:
    """The single run-level action the engine takes after DECIDE."""

    action: DecisionAction  # done | retry | escalate | human_review | follow_up
    reason: str
    task_ids: tuple[str, ...] = ()  # tasks to (re)dispatch on retry/follow_up


def latest_verdict_by_task(run: RunPaths) -> dict[str, CriticVerdict]:
    """Return the most-recent persisted verdict per task_id (later lines win)."""
    latest: dict[str, CriticVerdict] = {}
    for verdict in read_critic_verdicts(run.root):
        if verdict.task_id:
            latest[verdict.task_id] = verdict
    return latest


def undispatched_task_ids(run: RunPaths) -> list[str]:
    """Planned task contracts that have no result yet (e.g. new coverage-gap follow-ups)."""
    have = {p.name[: -len(_RESULT_SUFFIX)] for p in run.results.glob(f"TASK-*{_RESULT_SUFFIX}")}
    planned = {p.stem for p in run.tasks.glob("TASK-*.yaml")}
    return sorted(planned - have)


def aggregate_decision(
    run: RunPaths,
    state: RunState,
    *,
    settings: SiftmeshSettings,
    exclude: frozenset[str] = frozenset(),
    verdicts: dict[str, CriticVerdict] | None = None,
) -> RunDecision:
    """Fold the per-task ``decide`` outcomes into one run-level :class:`RunDecision`.

    ``exclude`` drops task_ids from the fold - full-auto passes the quarantined tasks so one
    flagged task's ``human_review``/``escalate`` does not starve the others' retries/follow-ups.
    ``verdicts`` lets the caller pass a pre-read verdict map (B2): the quarantine loop calls this
    repeatedly and would otherwise re-read + re-validate ``critic_verdicts.jsonl`` each pass. The
    map is read-only here (only ``exclude`` changes between passes), so reuse is identical.
    """
    if verdicts is None:
        verdicts = latest_verdict_by_task(run)
    per_action: dict[str, DecisionAction] = {}
    for task_id, verdict in verdicts.items():
        if task_id in exclude:
            continue
        per_task = state.per_task.get(task_id, PerTaskState())
        per_action[task_id] = decide(
            verdict.verdict,
            attempt=per_task.attempt,
            max_attempts=per_task.max_attempts,
            iteration=state.iteration,
            max_iterations=state.max_iterations,
        ).action

    actions = set(per_action.values())
    if "human_review" in actions:
        ids = tuple(sorted(t for t, a in per_action.items() if a == "human_review"))
        return RunDecision("human_review", "a task requires human review", ids)
    if "escalate" in actions:
        ids = tuple(sorted(t for t, a in per_action.items() if a == "escalate"))
        return RunDecision("escalate", "a task escalated (contradiction / attempts exhausted)", ids)
    retry_ids = tuple(sorted(t for t, a in per_action.items() if a == "retry"))
    if retry_ids:
        return RunDecision("retry", "critic requested a stricter retry", retry_ids)
    pending = tuple(t for t in undispatched_task_ids(run) if t not in exclude)
    if pending:
        return RunDecision("follow_up", "uncovered artifacts have follow-up tasks", pending)
    return RunDecision("done", "all tasks accepted or downgraded", ())
