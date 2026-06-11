"""Cockpit data layer (Epic O) — the single, tested, Textual-FREE snapshot of a run.

``build_snapshot(run)`` reads ``run_state.json`` (``read_run_state``) + every ledger
(``load_report_view``) + the task contracts, derives the timers, and returns a frozen
``CockpitSnapshot`` holding exactly what the four cockpit zones render. The TUI is then a thin
renderer over this — so the cockpit's correctness is unit-tested here (against the golden run),
with no terminal. It NEVER raises on a half-written / not-yet-started run dir (returns an empty
snapshot), so polling a live run is safe. Pure reads only; no engine state is mutated.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime

from siftmesh_core.orchestrator.run_state_store import read_run_state
from siftmesh_core.orchestrator.state_machine import TRANSITIONS
from siftmesh_core.reports.loader import ReportView, load_report_view
from siftmesh_core.run_dir import RunPaths
from siftmesh_core.schemas.task import TaskContract
from siftmesh_core.schemas.yaml_io import read_yaml_model

# The FSM spine in ribbon order (dict preserves the definition order in state_machine.TRANSITIONS).
STAGE_ORDER: tuple[str, ...] = tuple(TRANSITIONS.keys())


@dataclass(frozen=True)
class StageCell:
    """One pipeline-ribbon cell."""

    name: str
    state: str  # "done" | "current" | "pending"
    seconds: float | None = None  # wall-clock spent in this stage (completed stages only)


@dataclass(frozen=True)
class TaskRow:
    """One row of the task-queue table (zone 3 left)."""

    task_id: str
    status: str  # pending | dispatched | <collect/critic status> | …
    attempt: int
    max_attempts: int
    family: str  # human label derived from the contract role
    agent: str  # profile/adapter that last ran it ("—" if not yet)
    claims: int  # promoted (confirmed+inferred) claims anchored to this task
    verdict: str  # latest critic verdict ("—" if none)
    claim_ids: tuple[str, ...] = ()  # claim ids anchored to this task (for drill-down)


@dataclass(frozen=True)
class ClaimRow:
    """One claim, for the claims-list table + drill-down (zone 3)."""

    claim_id: str
    status: str
    confidence: float
    task_id: str
    source_artifact: str
    text: str


@dataclass(frozen=True)
class AgentSession:
    """One agent-call summary (zone 3 right)."""

    task_id: str
    profile: str
    adapter: str
    status: str
    fell_back_from: str | None


@dataclass(frozen=True)
class EventRow:
    """One audit-ticker line (zone 4)."""

    lineno: int
    timestamp: str
    event: str
    summary: str


@dataclass(frozen=True)
class CockpitSnapshot:
    """Everything the cockpit renders, derived purely from the run-dir files."""

    run_id: str
    exists: bool  # False until run_state.json is first written (run just starting)
    # vitals (zone 1)
    mode: str
    stage: str
    blocked_gate: str | None
    current_agent: str
    iteration: int
    max_iterations: int
    tasks_done: int
    tasks_total: int
    total_elapsed_s: float
    stage_elapsed_s: float
    terminal: bool
    quarantined: tuple[str, ...]
    # pipeline (zone 2)
    pipeline: tuple[StageCell, ...]
    # working area (zone 3)
    tasks: tuple[TaskRow, ...]
    claim_counts: dict[str, int]  # confirmed/inferred/contradicted/unsupported
    verdict_tally: dict[str, int]
    agent_sessions: tuple[AgentSession, ...]
    budget: tuple[dict[str, object], ...]
    claims: tuple[ClaimRow, ...]  # all claims (incl. unsupported) for the list + drill-down
    # audit ticker (zone 4) + the other selectable ledgers
    events: tuple[EventRow, ...]
    ledger_lines: dict[str, tuple[EventRow, ...]]  # name -> rows (events/tool-calls/agent-calls/…)
    load_errors: tuple[str, ...]


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _seconds(a: datetime | None, b: datetime | None) -> float:
    if a is None or b is None:
        return 0.0
    return max(0.0, (a - b).total_seconds())


def _empty(run_id: str) -> CockpitSnapshot:
    pipeline = tuple(StageCell(name=s, state="pending") for s in STAGE_ORDER)
    return CockpitSnapshot(
        run_id=run_id,
        exists=False,
        mode="—",
        stage="init",
        blocked_gate=None,
        current_agent="—",
        iteration=0,
        max_iterations=0,
        tasks_done=0,
        tasks_total=0,
        total_elapsed_s=0.0,
        stage_elapsed_s=0.0,
        terminal=False,
        quarantined=(),
        pipeline=pipeline,
        tasks=(),
        claim_counts={"confirmed": 0, "inferred": 0, "contradicted": 0, "unsupported": 0},
        verdict_tally={},
        agent_sessions=(),
        budget=(),
        claims=(),
        events=(),
        ledger_lines={},
        load_errors=(),
    )


def _load_contracts(run: RunPaths) -> list[TaskContract]:
    """Enumerate the run's task contracts (tolerant: a half-written YAML is skipped)."""
    contracts: list[TaskContract] = []
    for path in sorted(run.tasks.glob("TASK-*.yaml")):
        try:
            contracts.append(read_yaml_model(TaskContract, path))
        except Exception:  # a mid-write contract must not crash the cockpit
            continue
    return contracts


def _family(role: str) -> str:
    """Short family label from the contract role (e.g. 'evtx_security_executor' → 'evtx')."""
    return role.removesuffix("_executor") or role


def _pipeline(stage: str, terminal: bool, events: tuple) -> tuple[StageCell, ...]:
    durations = _stage_durations(events)
    try:
        cur = STAGE_ORDER.index(stage)
    except ValueError:
        cur = 0
    cells: list[StageCell] = []
    for i, name in enumerate(STAGE_ORDER):
        if terminal or i < cur:
            cstate = "done"
        elif i == cur:
            cstate = "current"
        else:
            cstate = "pending"
        cells.append(StageCell(name=name, state=cstate, seconds=durations.get(name)))
    return tuple(cells)


def _stage_durations(events: tuple) -> dict[str, float]:
    """Per-stage wall-clock from consecutive ``transition`` events (from_state/to_state + ts)."""
    entered: dict[str, datetime] = {}
    durations: dict[str, float] = {}
    for ev in events:
        if ev.event != "transition":
            continue
        ts = _parse_iso(ev.timestamp)
        if ts is None:
            continue
        frm = str(ev.extra.get("from_state", ""))
        to = str(ev.extra.get("to_state", ""))
        if frm in entered:
            durations[frm] = _seconds(ts, entered[frm])
        if to:
            entered[to] = ts
    return durations


def _budget(run: RunPaths) -> tuple[dict[str, object], ...]:
    """Best-effort raw read of the budget-router ledger (no dedicated reader)."""
    path = run.token_budget
    if not path.is_file():
        return ()
    rows: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(obj, dict):
            rows.append(obj)
    return tuple(rows)


def _stage_from_events(events: tuple) -> tuple[str, bool]:
    """Derive (current stage, terminal) from the transition event stream (no run_state present)."""
    stage = "init"
    terminal = False
    for ev in events:
        if ev.event == "transition":
            to = str(ev.extra.get("to_state", "")) or stage
            stage = to
            if to == "done":
                terminal = True
    return stage, terminal


def _entry_ts(events: tuple, stage: str) -> datetime | None:
    """Timestamp of the last transition INTO ``stage`` (for the stage timer without run_state)."""
    found: datetime | None = None
    for ev in events:
        if ev.event == "transition" and str(ev.extra.get("to_state", "")) == stage:
            ts = _parse_iso(ev.timestamp)
            if ts is not None:
                found = ts
    return found


def build_snapshot(run: RunPaths, *, now: datetime | None = None) -> CockpitSnapshot:
    """Build the cockpit snapshot from the run-dir files; safe on a not-yet-started run.

    ``run_state.json`` is OPTIONAL — a completed run recorded without it (or a live run before its
    first transition write) still renders from the ledgers (events/claims/agent_calls/verdicts).
    """
    now = now or datetime.now(UTC)
    state = None
    if run.run_state.is_file():
        try:
            state = read_run_state(run)
        except Exception:  # mid-write run_state: fall back to ledger-only, never crash
            state = None
    view: ReportView = load_report_view(run, strict=False)
    contracts = _load_contracts(run)

    if state is None and not view.events and not view.agent_calls and not contracts:
        return _empty(run.run_id)  # truly nothing yet

    stage: str
    mode: str
    if state is not None:
        stage, terminal = state.state, state.terminal
        mode, iteration, max_iterations = state.mode, state.iteration, state.max_iterations
        blocked_gate = state.blocked_gate
        quarantined = tuple(state.quarantined_tasks)
        per_task = state.per_task
        stage_entry = state.updated_utc
    else:
        stage, terminal = _stage_from_events(view.events)
        mode, iteration, max_iterations = "—", 0, 0
        blocked_gate = None
        quarantined = ()
        per_task = {}
        stage_entry = _entry_ts(view.events, stage)

    # timers: stage = time since entering the current state; total = since the first event.
    first_ts = _parse_iso(view.events[0].timestamp) if view.events else stage_entry
    last_ts = _parse_iso(view.events[-1].timestamp) if view.events else stage_entry
    end_ref = now if not terminal else (last_ts or now)
    total_elapsed = _seconds(end_ref, first_ts)
    stage_elapsed = _seconds(end_ref, stage_entry)
    dispatched = {a.task_id for a in view.agent_calls}
    promoted_by_task: dict[str, int] = {}
    claim_ids_by_task: dict[str, list[str]] = {}
    for claim in (*view.confirmed, *view.inferred):
        if claim.task_id:
            promoted_by_task[claim.task_id] = promoted_by_task.get(claim.task_id, 0) + 1
    for claim in (*view.confirmed, *view.inferred, *view.contradicted, *view.unsupported):
        if claim.task_id:
            claim_ids_by_task.setdefault(claim.task_id, []).append(claim.claim_id)
    latest_agent_for: dict[str, tuple[str, str]] = {}
    for call in view.agent_calls:  # sorted by AGENT-NNN ⇒ chronological; last wins
        latest_agent_for[call.task_id] = (call.profile, call.adapter)

    tasks: list[TaskRow] = []
    done = 0
    for c in contracts:
        per = per_task.get(c.task_id)
        if per is not None and per.status not in ("", "pending"):
            status = per.status
        elif c.task_id in dispatched:
            status = "dispatched"
        else:
            status = "pending"
        if status not in ("pending",):
            done += 1
        agent = latest_agent_for.get(c.task_id)
        verdict = view.verdict_by_task_id.get(c.task_id)
        tasks.append(
            TaskRow(
                task_id=c.task_id,
                status=status,
                attempt=per.attempt if per else 1,
                max_attempts=per.max_attempts if per else c.retry_policy.max_attempts,
                family=_family(c.role),
                agent=f"{agent[0]}" if agent else "—",
                claims=promoted_by_task.get(c.task_id, 0),
                verdict=verdict.verdict if verdict else "—",
                claim_ids=tuple(claim_ids_by_task.get(c.task_id, ())),
            )
        )

    current_agent = "—"
    if view.agent_calls:
        last_call = view.agent_calls[-1]
        current_agent = last_call.profile

    sessions = tuple(
        AgentSession(
            task_id=a.task_id,
            profile=a.profile,
            adapter=a.adapter,
            status=a.status,
            fell_back_from=a.fell_back_from,
        )
        for a in view.agent_calls
    )
    events = tuple(
        EventRow(
            lineno=e.lineno,
            timestamp=e.timestamp,
            event=e.event,
            summary=_event_summary(e),
        )
        for e in view.events
    )
    claims = tuple(
        ClaimRow(
            claim_id=c.claim_id,
            status=c.status,
            confidence=c.confidence,
            task_id=c.task_id or "—",
            source_artifact=c.source_artifact or "—",
            text=c.claim,
        )
        for c in (*view.confirmed, *view.inferred, *view.contradicted, *view.unsupported)
    )
    budget = _budget(run)
    ledger_lines = {
        "events": events,
        "tool-calls": tuple(
            EventRow(
                i, str(t.start_time_utc), "tool_call", f"{t.tool_call_id} {t.tool_name} {t.status}"
            )
            for i, t in enumerate(view.tool_results)
        ),
        "agent-calls": tuple(
            EventRow(
                i,
                str(a.start_time_utc),
                "agent_call",
                f"{a.agent_call_id} {a.task_id} {a.profile} {a.status}",
            )
            for i, a in enumerate(view.agent_calls)
        ),
        "retries": tuple(
            EventRow(
                i,
                "",
                "retry",
                f"{r.task_id} attempt={getattr(r, 'from_attempt', '?')} {getattr(r, 'cause', '')}",
            )
            for i, r in enumerate(view.retries)
        ),
        "token-budget": tuple(
            EventRow(
                i,
                str(b.get("timestamp", "")),
                "budget",
                f"{b.get('base_profile', '?')} -> {b.get('selected_profile', '?')}",
            )
            for i, b in enumerate(budget)
        ),
    }

    return CockpitSnapshot(
        run_id=run.run_id,
        exists=True,
        mode=mode,
        stage=stage,
        blocked_gate=blocked_gate,
        current_agent=current_agent,
        iteration=iteration,
        max_iterations=max_iterations,
        tasks_done=done,
        tasks_total=len(contracts),
        total_elapsed_s=total_elapsed,
        stage_elapsed_s=stage_elapsed,
        terminal=terminal,
        quarantined=quarantined,
        pipeline=_pipeline(stage, terminal, view.events),
        tasks=tuple(tasks),
        claim_counts={
            "confirmed": len(view.confirmed),
            "inferred": len(view.inferred),
            "contradicted": len(view.contradicted),
            "unsupported": len(view.unsupported),
        },
        verdict_tally=view.verdict_tally,
        agent_sessions=sessions,
        budget=budget,
        claims=claims,
        events=events,
        ledger_lines=ledger_lines,
        load_errors=view.load_errors,
    )


def run_badge(run: RunPaths) -> str:
    """A one-word status for the home run-list (Textual-free, tolerant): what state is this run in?

    ``terminal`` (done) · ``blocked:<gate>`` (awaiting approval) · ``paused`` (cooperatively
    halted) · ``running`` (mid-flight) · ``new`` (no state yet). Badges runs + offers Resume.
    """
    if not run.run_state.is_file():
        return "new"
    try:
        state = read_run_state(run)
    except Exception:
        return "new"
    if state.terminal:
        return "terminal"
    if state.blocked_gate:
        return f"blocked:{state.blocked_gate}"
    # paused = the last orchestration event is a cooperative pause (no later transition/completion).
    if run.orchestration_events.is_file():
        for line in reversed(run.orchestration_events.read_text(encoding="utf-8").splitlines()):
            if not line.strip():
                continue
            try:
                ev = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            if ev.get("event") in ("transition", "run_complete", "halted", "gate_blocked"):
                break
            if ev.get("event") == "paused":
                return "paused"
            break
    return "running"


def resumable(run: RunPaths) -> bool:
    """True if the run can be resumed/driven from the home screen (not terminal, has state)."""
    return run_badge(run) not in ("terminal", "new")


def _event_summary(ev: object) -> str:
    """A compact one-line summary of an orchestration event for the ticker."""
    name = getattr(ev, "event", "")
    extra = getattr(ev, "extra", {}) or {}
    keys = ("from_state", "to_state", "task_id", "profile", "verdict", "action", "gate", "reason")
    parts = [f"{k}={extra[k]}" for k in keys if k in extra]
    return f"{name} {' '.join(parts)}".strip()
