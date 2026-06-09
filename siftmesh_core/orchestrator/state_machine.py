"""Deterministic state-machine transition table (H2).

A frozen successor map over :data:`RunStateName` plus a pure ``step`` that rejects any
transition not in the table. This module is the *authoritative legality oracle* — the engine
(``workflow_runner``) proposes the next state, this code decides whether it is legal
("LLM proposes, code decides"). No I/O, no side effects, fully deterministic.

The only branch is at ``decide``: a retry/follow-up loops back to ``dispatch``, a ``done``
verdict advances to ``report``, and an escalate/human-review halts *at* ``decide`` awaiting a
human (a halt, not a transition). ``plan`` short-circuits to ``done`` in review-only mode.
"""

from __future__ import annotations

from siftmesh_core.schemas.decision import DecisionAction
from siftmesh_core.schemas.run import RunStateName

TERMINAL: RunStateName = "done"

# Frozen successor map. Membership here is the sole definition of a legal transition.
TRANSITIONS: dict[RunStateName, frozenset[RunStateName]] = {
    "init": frozenset({"create_evidence_vault"}),
    "create_evidence_vault": frozenset({"deep_context"}),
    "deep_context": frozenset({"plan"}),
    "plan": frozenset({"dispatch", "done"}),  # done only in review-only mode
    "dispatch": frozenset({"collect"}),
    "collect": frozenset({"critique"}),
    "critique": frozenset({"decide"}),
    "decide": frozenset({"dispatch", "report", "done"}),  # loop | proceed | (review-only) end
    "report": frozenset({"done"}),
    "done": frozenset(),
}


class IllegalTransitionError(RuntimeError):
    """Raised when a proposed transition is not in the frozen TRANSITIONS table."""


def legal_successors(current: RunStateName) -> frozenset[RunStateName]:
    """Return the set of states reachable in one legal step from ``current``."""
    return TRANSITIONS[current]


def step(current: RunStateName, target: RunStateName) -> RunStateName:
    """Return ``target`` iff ``current -> target`` is legal, else raise."""
    if target not in TRANSITIONS[current]:
        allowed = ", ".join(sorted(TRANSITIONS[current])) or "<terminal>"
        raise IllegalTransitionError(
            f"illegal transition {current!r} -> {target!r}; allowed: {allowed}"
        )
    return target


def next_state(
    current: RunStateName,
    *,
    review_only: bool = False,
    decision: DecisionAction | None = None,
) -> RunStateName:
    """Compute the natural successor for the linear spine + the ``decide`` branch.

    Returns ``current`` unchanged to signal a *halt* (terminal ``done``, or a
    ``decide`` escalate/human-review that awaits a human). Every non-halt result is
    validated through :func:`step`, so an illegal successor can never be returned.
    """
    if current == TERMINAL:
        return current
    if current == "plan":
        return step(current, "done" if review_only else "dispatch")
    if current == "decide":
        if decision in ("retry", "follow_up"):
            return step(current, "dispatch")
        if decision == "done":
            return step(current, "report")
        return current  # escalate / human_review / None -> halt at decide
    successors = TRANSITIONS[current]
    if len(successors) != 1:  # defensive: the spine outside plan/decide is single-successor
        raise IllegalTransitionError(f"ambiguous successor for {current!r}: {sorted(successors)}")
    return step(current, next(iter(successors)))
