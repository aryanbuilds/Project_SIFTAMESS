"""Deterministic DECIDE function (Epic G, G4) - "code decides".

``decide`` is a **pure function** (no I/O) implementing CLAUDE.md §12 verbatim: it
maps a critic verdict + run/task facts to one of four actions (done / retry /
escalate / human_review). The caller (the ``retry`` CLI now; the Epic-H runner
later) supplies the runtime facts as scalars/booleans, so the same frozen table
governs every mode. This is the criterion-4 "the deterministic engine decides
whether an LLM-proposed action is legal" evidence.
"""

from __future__ import annotations

from siftmesh_core.schemas.audit import CriticVerdictType
from siftmesh_core.schemas.decision import Decision


def decide(
    verdict: CriticVerdictType,
    *,
    attempt: int,
    max_attempts: int,
    iteration: int = 0,
    max_iterations: int = 3,
    has_contradiction: bool = False,
    prior_attempts_failed: bool = False,
    unsupported_affects_report: bool = False,
    injection_affected: bool = False,
    evidence_mismatch: bool = False,
    coverage_gap: bool = False,
    needs_corroboration: bool = False,
) -> Decision:
    """Map (verdict, run/task facts) → a Decision. Pure; CLAUDE §12.

    Rows are evaluated top-to-bottom, first match wins. Order encodes precedence:
    human-stops > escalate > done > retry.
    """
    # 1-4: stop and ask a human (CLAUDE §12 "Stop and ask human if").
    if evidence_mismatch:
        return Decision(
            action="human_review",
            reason="evidence path/hash mismatch - possible evidence modification",
        )
    if injection_affected or verdict == "human_review_required":
        return Decision(
            action="human_review",
            reason="evidence text appears to manipulate agent instructions",
        )
    if iteration >= max_iterations:
        return Decision(action="human_review", reason="max iterations reached")
    if unsupported_affects_report:
        return Decision(
            action="human_review", reason="unsupported claim would affect the final report"
        )

    # 4b: coverage/corroboration gap on an otherwise-accepted task → do MORE work, not "done"
    # (G9 - "recognize gaps and adjust": examine another artifact / gather corroboration).
    if (coverage_gap or needs_corroboration) and verdict in ("accepted", "accepted_with_downgrade"):
        reason = "examine another artifact" if coverage_gap else "gather corroboration"
        return Decision(action="follow_up", reason=reason)

    # 5: done (CLAUDE §12 "Mark task done if").
    if verdict in ("accepted", "accepted_with_downgrade"):
        return Decision(action="done", reason="critic accepted")

    # 6-7,9-10: escalate (CLAUDE §12 "Escalate task if").
    if has_contradiction or verdict == "escalation_required":
        return Decision(action="escalate", reason="contradiction affects a major finding")
    if prior_attempts_failed and verdict == "retry_required":
        return Decision(action="escalate", reason="same task failed twice")

    # 8: retry (CLAUDE §12 "Retry task if"), gated by the per-task attempt cap.
    if verdict == "retry_required":
        if attempt < max_attempts:
            return Decision(
                action="retry",
                reason="claim lacks evidence reference / critic requests a stricter schema",
                tighten_success_criteria=True,
            )
        return Decision(action="escalate", reason="retry budget exhausted")

    if verdict == "rejected":
        return Decision(action="escalate", reason="rejected and not auto-retryable")

    # 11: defensive fail-safe (keeps the function total).
    return Decision(action="human_review", reason=f"unhandled verdict: {verdict}")
