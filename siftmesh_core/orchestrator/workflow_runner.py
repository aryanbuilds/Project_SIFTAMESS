"""Deterministic workflow runner (H3-H6, H8) — the Ultraworker engine.

``run_engine`` drives one run through the frozen state machine
(init → create_evidence_vault → deep_context → plan → dispatch → collect → critique → decide →
{loop | report} → done), calling the already-built Epic E/F/G stages, enforcing caps (H4),
honouring approval gates (H5), persisting ``RunState`` atomically after every transition (H1),
and emitting one orchestration event per transition/decision (H8). No LLM, fully deterministic.

Mode policy (set by the caller via ``RunState.mode`` + ``single_step``):
  * ``manual``          — one transition per call (``single_step=True``); gates auto-pass.
  * ``review_only``     — plan, then stop (dispatch unreachable); gates auto-pass.
  * ``auto_human_loop`` — run until a pending meaningful gate, then halt for ``approve``.
  * ``auto``            — run to terminal; caps enforced; gates auto-pass.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path

from structlog.typing import FilteringBoundLogger

from siftmesh_core.config import SiftmeshSettings
from siftmesh_core.evidence.decompress import decompress_archive
from siftmesh_core.evidence.derived import read_derived
from siftmesh_core.ledgers.audit_log import log_event, open_orchestration_log
from siftmesh_core.mcp_gateway.backends import BackendUnavailableError
from siftmesh_core.orchestrator.artifact_router import route_manifest
from siftmesh_core.orchestrator.budget_router import record_routing, select_profile
from siftmesh_core.orchestrator.critic import critique_run, write_retry
from siftmesh_core.orchestrator.planner import generate_plan
from siftmesh_core.orchestrator.run_state_store import read_run_state, write_run_state
from siftmesh_core.orchestrator.scheduler import (
    collect_run,
    dispatch_run,
    recover_evidence_root,
)
from siftmesh_core.orchestrator.state_machine import IllegalTransitionError, next_state, step
from siftmesh_core.orchestrator.ultraworker import (
    aggregate_decision,
    latest_verdict_by_task,
    undispatched_task_ids,
)
from siftmesh_core.run_dir import RunPaths
from siftmesh_core.schemas.audit import CriticVerdict
from siftmesh_core.schemas.evidence import EvidenceManifest
from siftmesh_core.schemas.run import GateName, PerTaskState, RunState, RunStateName
from siftmesh_core.schemas.task import TaskContract
from siftmesh_core.schemas.yaml_io import read_yaml_model


def _entry_gate(state_name: RunStateName, iteration: int) -> GateName | None:
    """The approval gate (if any) guarding entry to ``state_name`` (H5)."""
    if state_name == "dispatch":
        return "plan" if iteration == 0 else "retry"
    if state_name == "report":
        return "report"
    return None


def _init_per_task(run: RunPaths, state: RunState) -> RunState:
    """Seed per-task attempt bookkeeping from the planned contracts (after PLAN)."""
    per_task = dict(state.per_task)
    for path in sorted(run.tasks.glob("TASK-*.yaml")):
        contract = read_yaml_model(TaskContract, path)
        per_task.setdefault(
            path.stem, PerTaskState(max_attempts=contract.retry_policy.max_attempts)
        )
    return state.model_copy(update={"per_task": per_task})


def _auto_handle_archives(
    run: RunPaths, *, evidence_root: Path, audit: FilteringBoundLogger
) -> None:
    """Auto-decompress pre-existing archive evidence (e.g. a zipped memory capture) in full-auto.

    Without this, a ``.zip`` in the evidence set is non-actionable (the planner has no in-place
    tool) and the operator had to run ``decompress`` + ``ingest-derived`` by hand. Here each
    archive is decompressed once; the registered derived image is then picked up by the existing
    critique-driven derived re-ingest (G9), so the full-auto loop covers it end to end. Idempotent
    (skips archives already decompressed — safe on resume); fail-soft (a missing ``7z`` / failed
    decompress is logged and skipped, never killing the run). bd 48me.
    """
    if not run.evidence_manifest.is_file():
        return
    manifest = EvidenceManifest.model_validate_json(
        run.evidence_manifest.read_text(encoding="utf-8")
    )
    already = {d.source_artifact for d in read_derived(run.root)}
    for art in route_manifest(manifest):
        if art.family != "archive" or art.path in already:
            continue
        try:
            outcome = decompress_archive(run, archive=art.path, evidence_root=evidence_root)
        except (BackendUnavailableError, RuntimeError, ValueError, OSError) as exc:
            log_event(audit, "archive_decompress_skipped", archive=art.path, reason=str(exc))
            continue
        log_event(
            audit,
            "archive_auto_decompress",
            archive=art.path,
            decomp_id=outcome.decomp_id,
            derived_path=outcome.derived_path,
        )


def _advance(
    run: RunPaths,
    state: RunState,
    *,
    settings: SiftmeshSettings,
    evidence_root: Path,
    audit: FilteringBoundLogger,
) -> tuple[RunState, RunStateName]:
    """Execute the current state's stage; return (updated_state, next_state).

    A returned next-state equal to the current state signals a *halt* (decide →
    escalate/human-review, or a cap stop): the engine persists and stops for a human.
    """
    current = state.state
    review_only = state.mode == "review_only"

    if current == "init":
        return state, next_state(current)
    if current == "create_evidence_vault":
        if not run.evidence_manifest.is_file():
            raise FileNotFoundError(f"no evidence manifest at {run.evidence_manifest}")
        # Full-auto modes prepare archive evidence themselves (the "one command" promise);
        # manual/review-only operators use the explicit `decompress`/`ingest-derived` commands.
        if state.mode in ("auto", "auto_human_loop"):
            _auto_handle_archives(run, evidence_root=evidence_root, audit=audit)
        return state, next_state(current)
    if current == "deep_context":
        return state, next_state(current)  # the deep-context pack is produced by the planner
    if current == "plan":
        generate_plan(run, settings=settings, review_only=review_only)
        state = _init_per_task(run, state)
        return state, next_state(current, review_only=review_only)
    if current == "dispatch":
        refs = []
        if state.iteration == 0:
            refs = dispatch_run(run, settings=settings, evidence_override=evidence_root)
        else:
            verdicts = latest_verdict_by_task(run)
            for task_id in state.pending_dispatch:
                task_state = state.per_task.get(task_id, PerTaskState())
                feedback = tuple(verdicts[task_id].reasons) if task_id in verdicts else ()
                refs += dispatch_run(
                    run,
                    settings=settings,
                    evidence_override=evidence_root,
                    task_id=task_id,
                    attempt=task_state.attempt,
                    critic_feedback=feedback,
                )
        state = state.model_copy(
            update={
                "agent_tasks_completed": state.agent_tasks_completed + len(refs),
                "pending_dispatch": [],
            }
        )
        return state, next_state(current)
    if current == "collect":
        report = collect_run(run)
        per_task = dict(state.per_task)
        for row in report.rows:
            base = per_task.get(row.task_id, PerTaskState())
            per_task[row.task_id] = base.model_copy(update={"status": row.status})
        return state.model_copy(update={"per_task": per_task}), next_state(current)
    if current == "critique":
        critique_run(run, settings=settings, evidence_root=evidence_root, generate_followups=True)
        return state, next_state(current)
    if current == "decide":
        return _decide(run, state, settings=settings, evidence_root=evidence_root, audit=audit)
    if current == "report":
        if state.mode in ("auto", "auto_human_loop"):
            from siftmesh_core.reports import generate_all_reports

            try:
                paths = generate_all_reports(run, evidence_root=evidence_root, strict=True)
                log_event(
                    audit, "reports_generated", count=len(paths), files=[p.name for p in paths]
                )
            except Exception as exc:
                log_event(audit, "reports_failed", error=str(exc))
        else:
            log_event(audit, "report_skipped", reason="non-auto mode; run `siftmesh report <run>`")
        return state, next_state(current)
    raise IllegalTransitionError(f"no action defined for state {current!r}")


def _verdict_tally(verdicts: Mapping[str, CriticVerdict]) -> dict[str, int]:
    """Sorted verdict-type -> count (B4). Deterministic JSON (sorted keys, counts only)."""
    counts: dict[str, int] = {}
    for v in verdicts.values():
        counts[v.verdict] = counts.get(v.verdict, 0) + 1
    return dict(sorted(counts.items()))


def _decide(
    run: RunPaths,
    state: RunState,
    *,
    settings: SiftmeshSettings,
    evidence_root: Path,
    audit: FilteringBoundLogger,
) -> tuple[RunState, RunStateName]:
    """DECIDE: aggregate per-task verdicts → loop (retry/follow_up) | report | halt.

    Mode policy: ``auto_human_loop``/``manual`` HALT on a per-task human_review/escalate (a human
    resolves it off-engine). ``auto`` instead QUARANTINES the flagged task and proceeds — a single
    flagged task must not strand a 200-task run. The flagged claims were already kept out of the
    findings ledger by the critic (``_maybe_promote`` refuses ``_HUMAN``/``_REJECT``), so quarantine
    can never leak a fact; the items surface in the report's unsupported/injection appendices.
    """
    # B2: read the verdict map ONCE and reuse it across every aggregate_decision call below (the
    # quarantine loop would otherwise re-read + re-validate critic_verdicts.jsonl each pass). Map
    # is read-only here; only `exclude` changes per pass, so reuse is identical.
    verdicts = latest_verdict_by_task(run)
    tally = _verdict_tally(verdicts)  # B4: sorted/count-only enrichment (deterministic JSON)
    decision = aggregate_decision(run, state, settings=settings, verdicts=verdicts)
    log_event(
        audit,
        "decision",
        action=decision.action,
        reason=decision.reason,
        tasks=list(decision.task_ids),
        verdict_tally=tally,
        pending_count=len(undispatched_task_ids(run)),
        quarantined_count=len(state.quarantined_tasks),
    )
    # Full-auto: quarantine flagged task(s) and re-aggregate so the rest still runs. Each pass
    # quarantines ≥1 new task and excludes it from the next fold, so this terminates.
    while state.mode == "auto" and decision.action in ("escalate", "human_review"):
        quarantined = sorted(set(state.quarantined_tasks) | set(decision.task_ids))
        log_event(
            audit,
            "task_quarantined",
            tasks=list(decision.task_ids),
            reason=decision.reason,
            action=decision.action,
        )
        state = state.model_copy(update={"quarantined_tasks": quarantined})
        decision = aggregate_decision(
            run, state, settings=settings, exclude=frozenset(quarantined), verdicts=verdicts
        )
        log_event(
            audit,
            "decision",
            action=decision.action,
            reason=decision.reason,
            tasks=list(decision.task_ids),
            quarantined_count=len(quarantined),
            residual=True,
        )
    if decision.action == "done":
        return state, next_state("decide", decision="done")
    if decision.action in ("retry", "follow_up"):
        if state.iteration >= state.max_iterations:  # global cap (H4) — never loop unbounded
            # Hitting the cap means a task genuinely would not converge after max_iterations retry
            # loops — a real "stop and ask a human" signal (CLAUDE §12), distinct from the
            # single-flagged-task case the quarantine loop above already handles. Halt in all modes.
            log_event(audit, "cap_reached", cap="max_iterations", value=state.max_iterations)
            return state.model_copy(update={"blocked_gate": "retry"}), "decide"
        per_task = dict(state.per_task)
        if decision.action == "retry":
            routing = select_profile(
                settings.default_agent_profile, escalate=True, reason="critic_retry"
            )
            record_routing(run, routing, evidence_root=evidence_root)
            log_event(audit, "budget_routed", **routing.__dict__)
            for task_id in decision.task_ids:
                contract = read_yaml_model(TaskContract, run.tasks / f"{task_id}.yaml")
                base = per_task.get(task_id, PerTaskState())
                write_retry(
                    run,
                    contract,
                    from_attempt=base.attempt,
                    cause="critic_retry",
                    evidence_root=evidence_root,
                )
                per_task[task_id] = base.model_copy(update={"attempt": base.attempt + 1})
        state = state.model_copy(
            update={
                "iteration": state.iteration + 1,
                "pending_dispatch": list(decision.task_ids),
                "per_task": per_task,
            }
        )
        return state, next_state("decide", decision=decision.action)
    # escalate / human_review in guided/manual modes — halt for a human (resolvable off-engine).
    # (Full-auto can never reach here: the quarantine loop above resolved those actions.)
    return state.model_copy(update={"blocked_gate": "retry"}), "decide"


def run_engine(
    run: RunPaths,
    *,
    settings: SiftmeshSettings,
    evidence_root: Path | str | None = None,
    single_step: bool = False,
) -> RunState:
    """Drive the persisted RunState forward; return the (possibly halted/terminal) state."""
    state = read_run_state(run)
    audit = open_orchestration_log(run.orchestration_events, run.run_id)
    gates_enforced = state.mode == "auto_human_loop"
    evidence = Path(evidence_root) if evidence_root else recover_evidence_root(run)

    while not state.terminal:
        current = state.state
        gate = _entry_gate(current, state.iteration)
        if gate is not None:
            status = state.gates.get(gate, "pending")
            if status == "rejected":
                log_event(audit, "gate_rejected", gate=gate, state=current)
                return write_run_state(run, state.model_copy(update={"terminal": True}))
            if gates_enforced and status != "approved":
                log_event(audit, "gate_blocked", gate=gate, state=current)
                return write_run_state(run, state.model_copy(update={"blocked_gate": gate}))
            if gates_enforced:
                log_event(audit, "gate_approved", gate=gate, state=current)
            reset = dict(state.gates)
            reset[gate] = "pending"  # re-gate the next loop (matters for retry)
            state = state.model_copy(update={"gates": reset, "blocked_gate": None})

        stage_start = datetime.now(UTC)
        new_state, target = _advance(
            run, state, settings=settings, evidence_root=evidence, audit=audit
        )
        duration_ms = int((datetime.now(UTC) - stage_start).total_seconds() * 1000)
        if target == current:  # halt (escalate / human_review / cap)
            log_event(audit, "halted", state=current, blocked_gate=new_state.blocked_gate)
            return write_run_state(run, new_state)

        step(current, target)  # legality assertion ("code decides")
        terminal = target == "done"
        state = write_run_state(
            run, new_state.model_copy(update={"state": target, "terminal": terminal})
        )
        # B3: per-stage wall-clock on the transition event. Engine-only channel — the golden
        # recorder never runs run_engine, so these timed events never enter the golden bodies.
        log_event(
            audit,
            "transition",
            from_state=current,
            to_state=target,
            iteration=state.iteration,
            duration_ms=duration_ms,
        )
        if terminal:
            log_event(audit, "run_complete", run=run.run_id)
            break
        if single_step:
            break
    return state
