"""Deterministic Layer-1 Critic + self-correction governance (Epic G, G1/G2/G3/G6/G8).

``critique_run`` validates the Claims Epic F's executor produced (per-task
``results/TASK-*.result.json`` envelopes), emits one :class:`CriticVerdict` per task,
detects contradictions, downgrades over-broad claims, applies the injection
consequence, and persists verdicts/contradictions/confidence-changes — all
deterministically, no LLM. ``decide()`` (``orchestrator/decide.py``) consumes the
verdict. The optional Layer-2 LLM adversarial pass (G8) is a no-op seam here.

Write policy (the key correctness rule): Epic F's deterministic floor ALREADY
appended its claims to the claim ledger, so the critic VALIDATES those (never
re-appends — a structural no-dup guard by claim_id). Live-agent results carry
claims not yet in the ledger, so for those the critic IS the promoter. The genuine
live self-correction HERO is human-gated (Epic F8); here the governance is exercised
deterministically.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

from structlog.typing import FilteringBoundLogger

from siftmesh_core.adapters.spotlight import scan_injection
from siftmesh_core.config import SiftmeshSettings
from siftmesh_core.evidence.path_policy import safe_write_path
from siftmesh_core.ledgers.audit_log import log_event, open_orchestration_log
from siftmesh_core.ledgers.claim_ledger import (
    append_claim,
    read_claims,
    read_unsupported_claims,
)
from siftmesh_core.ledgers.confidence_changes import (
    append_confidence_change,
    next_confidence_change_id,
)
from siftmesh_core.ledgers.contradiction_ledger import append_contradiction, read_contradictions
from siftmesh_core.ledgers.critic_verdicts import append_critic_verdict, next_verdict_id
from siftmesh_core.ledgers.injection_alerts import (
    append_injection_alert,
    next_alert_id,
    read_injection_alerts,
)
from siftmesh_core.ledgers.retries import append_retry, next_retry_id
from siftmesh_core.mcp_gateway.tools.validation_tools import grade_claim_against_run
from siftmesh_core.run_dir import RunPaths
from siftmesh_core.schemas.audit import CriticVerdict, CriticVerdictType
from siftmesh_core.schemas.claim import Claim
from siftmesh_core.schemas.critic_records import ConfidenceChange, ContradictionRecord, RetryRecord
from siftmesh_core.schemas.injection_alert import InjectionAlert
from siftmesh_core.schemas.task import TaskContract
from siftmesh_core.schemas.task_result import TaskResult
from siftmesh_core.schemas.yaml_io import dump_yaml_model

# Per-claim outcomes (the verdict is derived from these + cross-cutting flags).
_ACCEPT, _DOWNGRADE, _UNSUPPORTED, _REJECT, _HUMAN = (
    "accept",
    "downgrade",
    "unsupported",
    "reject",
    "human_review",
)

# Over-broad / severity-overreach tokens (CLAUDE §10 "claim broader than evidence").
_QUANTIFIERS = re.compile(r"\b(all|every|always|none|never)\b", re.IGNORECASE)
_SEVERITY = re.compile(
    r"\b(critical|high severity|confirmed compromise|malicious|definitely)\b", re.IGNORECASE
)
_DOWNGRADE_FACTOR = 0.5


def _now() -> datetime:
    return datetime.now(UTC)


def _is_broader_than_evidence(claim: Claim) -> bool:
    """Structural over-breadth: an unconfirmed claim asserting a quantifier or final severity."""
    if claim.status == "confirmed":
        return False
    return bool(_QUANTIFIERS.search(claim.claim) or _SEVERITY.search(claim.claim))


def _injection_affected(claim: Claim, alerts: list[InjectionAlert]) -> bool:
    """Artifact-scoped: an alert on THIS claim's task+artifact, or injection text in the claim."""
    for alert in alerts:
        if alert.task_id == claim.task_id and alert.source_artifact == claim.source_artifact:
            return True
    blob = claim.claim + " " + " ".join(claim.supporting_evidence_refs)
    return bool(scan_injection(blob))


def _detect_contradictions(claims: list[Claim]) -> dict[str, ContradictionRecord]:
    """Deterministic, low-false-positive contradiction detection (no LLM).

    Rule 1 (same_artifact_field_value_mismatch): two claims with the same
    ``source_artifact`` + ``evidence_type`` whose texts share a digit-masked template
    but carry different numbers (e.g. "executed 3 time(s)" vs "executed 5 time(s)").
    Rule 2 (same_subject_opposite_assertion): a ``confirmed`` and a ``contradicted``
    claim on the same (source_artifact, evidence_type). Semantic contradiction is
    out of scope (G8/Layer-2).
    """
    anchored = [c for c in claims if c.status in ("confirmed", "inferred", "contradicted")]
    by_artifact: dict[tuple[str, str], list[Claim]] = {}
    for c in anchored:
        if c.source_artifact is None:
            continue
        by_artifact.setdefault((c.source_artifact, c.evidence_type), []).append(c)

    found: dict[str, ContradictionRecord] = {}
    n = 0
    for (artifact, etype), group in by_artifact.items():
        if len(group) < 2:
            continue
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                a, b = group[i], group[j]
                rule = _contradiction_rule(a, b)
                if rule is None:
                    continue
                n += 1
                rec = ContradictionRecord(
                    contradiction_id=f"CONTRA-{n:03d}",
                    task_id=b.task_id,
                    claim_id_a=a.claim_id,
                    claim_id_b=b.claim_id,
                    rule=rule,
                    subject=f"{artifact}|{etype}",
                    detail=f"{a.claim!r} vs {b.claim!r}",
                    detected_utc=_now(),
                )
                found[a.claim_id] = rec
                found[b.claim_id] = rec
    return found


def _contradiction_rule(a: Claim, b: Claim) -> str | None:
    if {a.status, b.status} == {"confirmed", "contradicted"}:
        return "same_subject_opposite_assertion"
    mask = re.compile(r"\d+")
    if mask.sub("N", a.claim) == mask.sub("N", b.claim) and mask.findall(a.claim) != mask.findall(
        b.claim
    ):
        return "same_artifact_field_value_mismatch"
    return None


def _classify_claim(run: RunPaths, claim: Claim, *, injection: bool, contradicted: bool) -> str:
    problems = grade_claim_against_run(run.root, claim)
    if problems:
        return _REJECT
    if injection:
        return _HUMAN
    if claim.status == "unsupported":
        return _UNSUPPORTED
    if contradicted or _is_broader_than_evidence(claim):
        return _DOWNGRADE
    return _ACCEPT


def _task_verdict(
    outcomes: list[str], *, has_contradiction: bool
) -> tuple[CriticVerdictType, list[str]]:
    """Map per-claim outcomes (+ contradiction) to one task verdict (precedence-ordered)."""
    if _HUMAN in outcomes:
        return "human_review_required", ["injection-affected claim requires human review"]
    if has_contradiction:
        return "escalation_required", ["a claim contradicts another"]
    if _REJECT in outcomes or _UNSUPPORTED in outcomes:
        return "retry_required", ["a claim is unsupported or lacks its evidence anchor"]
    if _DOWNGRADE in outcomes:
        return "accepted_with_downgrade", ["a claim was downgraded (over-broad)"]
    return "accepted", ["all claims evidence-anchored"]


def critique_run(
    run: RunPaths, *, settings: SiftmeshSettings, evidence_root: Path | str | None = None
) -> list[CriticVerdict]:
    """Critique every collected task result; persist verdicts + records; return verdicts."""
    audit = open_orchestration_log(run.orchestration_events, run.run_id)
    result_paths = sorted(run.results.glob("TASK-*.result.json"))

    # Pass 1: gather anchored claims across all success results → contradiction map.
    results: list[tuple[Path, TaskResult | None]] = []
    all_claims: list[Claim] = []
    for path in result_paths:
        try:
            tr = TaskResult.model_validate_json(path.read_text(encoding="utf-8"))
        except ValueError:
            results.append((path, None))
            continue
        results.append((path, tr))
        if tr.status == "success":
            all_claims.extend(tr.claims)
    contradictions = _detect_contradictions(all_claims)
    alerts = read_injection_alerts(run.root)
    persisted_ids = {c.claim_id for c in read_claims(run.root)} | {
        c.claim_id for c in read_unsupported_claims(run.root)
    }

    # Pass 2: per-task verdict.
    verdicts: list[CriticVerdict] = []
    for path, tr_opt in results:
        if tr_opt is None:
            verdicts.append(
                _persist_verdict(
                    run,
                    task_id=path.stem.replace(".result", ""),
                    verdict="retry_required",
                    reasons=["malformed result JSON"],
                    affected=[],
                    evidence_root=evidence_root,
                    audit=audit,
                )
            )
            continue
        tr = tr_opt
        if tr.status == "error":
            verdicts.append(
                _persist_verdict(
                    run,
                    task_id=tr.task_id,
                    verdict="escalation_required",
                    reasons=tr.errors or ["task errored"],
                    affected=[],
                    evidence_root=evidence_root,
                    audit=audit,
                )
            )
            continue
        if tr.status == "retry_required":
            verdicts.append(
                _persist_verdict(
                    run,
                    task_id=tr.task_id,
                    verdict="retry_required",
                    reasons=[tr.retry_cause or "recoverable tool error"],
                    affected=[],
                    evidence_root=evidence_root,
                    audit=audit,
                )
            )
            continue

        outcomes: list[str] = []
        affected: list[str] = []
        task_has_contradiction = False
        for claim in tr.claims:
            injected = _injection_affected(claim, alerts)
            contradicted = claim.claim_id in contradictions
            outcome = _classify_claim(run, claim, injection=injected, contradicted=contradicted)
            outcomes.append(outcome)
            if outcome != _ACCEPT:
                affected.append(claim.claim_id)
            if contradicted:
                task_has_contradiction = True
                _write_contradiction(run, contradictions[claim.claim_id], evidence_root, audit)
            if outcome == _DOWNGRADE:
                _write_downgrade(run, claim, evidence_root)
            if outcome == _HUMAN:
                _write_injection_consequence(run, claim, evidence_root, audit)
            _maybe_promote(run, tr, claim, outcome, persisted_ids, evidence_root)

        verdict_type, reasons = _task_verdict(outcomes, has_contradiction=task_has_contradiction)
        verdicts.append(
            _persist_verdict(
                run,
                task_id=tr.task_id,
                verdict=verdict_type,
                reasons=reasons,
                affected=affected,
                evidence_root=evidence_root,
                audit=audit,
            )
        )

    if settings.llm_critic_enabled:
        verdicts = llm_adversarial_review(verdicts, settings=settings)
    return verdicts


def _persist_verdict(
    run: RunPaths,
    *,
    task_id: str,
    verdict: CriticVerdictType,
    reasons: list[str],
    affected: list[str],
    evidence_root: Path | str | None,
    audit: FilteringBoundLogger,
) -> CriticVerdict:
    cv = CriticVerdict(
        verdict=verdict,
        reasons=reasons,
        affected_claim_ids=affected,
        task_id=task_id,
        verdict_id=next_verdict_id(run.root),
        decided_utc=_now(),
    )
    append_critic_verdict(run.root, cv, evidence_root=evidence_root)
    log_event(audit, "critic_verdict", task_id=task_id, verdict=verdict, affected=len(affected))
    return cv


def _write_contradiction(
    run: RunPaths,
    rec: ContradictionRecord,
    evidence_root: Path | str | None,
    audit: FilteringBoundLogger,
) -> None:
    existing = {r.contradiction_id for r in read_contradictions(run.root)}
    if rec.contradiction_id in existing:
        return
    append_contradiction(run.root, rec, evidence_root=evidence_root)
    log_event(audit, "contradiction_detected", contradiction_id=rec.contradiction_id, rule=rec.rule)


def _write_downgrade(run: RunPaths, claim: Claim, evidence_root: Path | str | None) -> None:
    to = round(claim.confidence * _DOWNGRADE_FACTOR, 4)
    append_confidence_change(
        run.root,
        ConfidenceChange(
            change_id=next_confidence_change_id(run.root),
            claim_id=claim.claim_id,
            task_id=claim.task_id,
            from_confidence=claim.confidence,
            to_confidence=to,
            reason="downgrade: claim broader than evidence or contradicted",
            changed_utc=_now(),
        ),
        evidence_root=evidence_root,
    )


def _write_injection_consequence(
    run: RunPaths, claim: Claim, evidence_root: Path | str | None, audit: FilteringBoundLogger
) -> None:
    append_injection_alert(
        run.root,
        InjectionAlert(
            alert_id=next_alert_id(run.root),
            source="critic",
            signature="claim_injection_affected",
            snippet=claim.claim[:200],
            detected_utc=_now(),
            task_id=claim.task_id,
            source_artifact=claim.source_artifact,
        ),
        evidence_root=evidence_root,
    )
    log_event(
        audit, "injection_consequence_applied", task_id=claim.task_id, claim_id=claim.claim_id
    )


def _maybe_promote(
    run: RunPaths,
    tr: TaskResult,
    claim: Claim,
    outcome: str,
    persisted_ids: set[str],
    evidence_root: Path | str | None,
) -> None:
    """Promote a LIVE-agent claim; floor claims are already persisted (no re-append)."""
    if claim.claim_id in persisted_ids:
        return  # floor result: F already appended it — validate-only, never duplicate
    if outcome in (_REJECT, _HUMAN):
        return  # rejected / human-review claims are not promoted
    append_claim(run.root, claim, evidence_root=evidence_root)
    persisted_ids.add(claim.claim_id)


# G5 — retry task generation -------------------------------------------------------

_TIGHTENED_CRITERIA = (
    "Every claim MUST include a tool_call_id and source_sha256 bound to a real tool call.",
    "Do not assert beyond the tool rows; no claim may exceed the evidence the tool returned.",
    "Do not assign final severity; report observations only.",
)


def generate_retry_contract(contract: TaskContract) -> TaskContract:
    """Return a deep copy with tightened success_criteria (idempotent). Pure (G5)."""
    tightened = list(contract.success_criteria)
    for line in _TIGHTENED_CRITERIA:
        if line not in tightened:
            tightened.append(line)
    return contract.model_copy(deep=True, update={"success_criteria": tightened})


def write_retry(
    run: RunPaths,
    contract: TaskContract,
    *,
    from_attempt: int,
    cause: str,
    evidence_root: Path | str | None = None,
) -> RetryRecord:
    """Overwrite the contract with the tightened version + record the retry (G5)."""
    tightened = generate_retry_contract(contract)
    target = safe_write_path(
        run.root, f"tasks/{contract.task_id}.yaml", evidence_root=evidence_root
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(dump_yaml_model(tightened), encoding="utf-8")
    record = RetryRecord(
        retry_id=next_retry_id(run.root),
        task_id=contract.task_id,
        from_attempt=from_attempt,
        to_attempt=from_attempt + 1,
        cause=cause,
        tightened_criteria=list(_TIGHTENED_CRITERIA),
        decided_utc=_now(),
    )
    append_retry(run.root, record, evidence_root=evidence_root)
    return record


def llm_adversarial_review(
    verdicts: list[CriticVerdict], *, settings: SiftmeshSettings
) -> list[CriticVerdict]:
    """Layer-2 LLM adversarial critic seam (G8) — IDENTITY/no-op, deferred.

    Behind ``settings.llm_critic_enabled`` (default off). The real pass needs the
    Epic-F8 agent adapter (``claude -p --output-format json`` via the isolated
    ``claude_adapter._build_claude_argv``); the Layer-1 deterministic verdicts are
    always complete and sufficient for the hero. Returns verdicts unchanged.
    """
    return verdicts
