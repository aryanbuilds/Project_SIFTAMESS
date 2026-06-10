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

import json
import re
from datetime import UTC, datetime
from pathlib import Path

from structlog.typing import FilteringBoundLogger

from siftmesh_core.adapters.claude_adapter import invoke_claude_text
from siftmesh_core.adapters.spotlight import scan_injection
from siftmesh_core.config import SiftmeshSettings
from siftmesh_core.evidence.derived import read_derived
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
from siftmesh_core.ledgers.followups import append_followup, next_followup_id
from siftmesh_core.ledgers.injection_alerts import (
    append_injection_alert,
    next_alert_id,
    read_injection_alerts,
)
from siftmesh_core.ledgers.retries import append_retry, next_retry_id
from siftmesh_core.mcp_gateway.tools.validation_tools import grade_claim_against_run
from siftmesh_core.orchestrator.artifact_router import (
    FineFamily,
    RoutedArtifact,
    route_manifest,
    route_path,
)
from siftmesh_core.orchestrator.planner import executor_contract, group_actionable
from siftmesh_core.run_dir import RunPaths
from siftmesh_core.schemas.audit import CriticVerdict, CriticVerdictType
from siftmesh_core.schemas.claim import Claim
from siftmesh_core.schemas.critic_records import (
    ConfidenceChange,
    ContradictionRecord,
    FollowupReason,
    FollowupRecord,
    RetryRecord,
)
from siftmesh_core.schemas.evidence import EvidenceManifest
from siftmesh_core.schemas.injection_alert import InjectionAlert
from siftmesh_core.schemas.plan import InvestigationPlan
from siftmesh_core.schemas.task import ArtifactOrigin, TaskContract
from siftmesh_core.schemas.task_result import TaskResult
from siftmesh_core.schemas.yaml_io import dump_yaml_model, read_yaml_model

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


def detect_contradictions(claims: list[Claim]) -> dict[str, ContradictionRecord]:
    """Public wrapper over the deterministic contradiction detector (reused by cross-run merge)."""
    return _detect_contradictions(claims)


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
    # Enumeration indices ("event #1" vs "event #2") mark DISTINCT items, not conflicting values —
    # strip them so per-item sibling claims on one artifact aren't mistaken for a value mismatch.
    enum = re.compile(r"#\s*\d+")
    a_text, b_text = enum.sub("#", a.claim), enum.sub("#", b.claim)
    mask = re.compile(r"\d+")
    if mask.sub("N", a_text) == mask.sub("N", b_text) and mask.findall(a_text) != mask.findall(
        b_text
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
    run: RunPaths,
    *,
    settings: SiftmeshSettings,
    evidence_root: Path | str | None = None,
    generate_followups: bool = True,
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

    # G9 — coverage/corroboration gaps ("recognize gaps and adjust").
    _record_corroboration_gaps(run, all_claims, evidence_root=evidence_root, audit=audit)
    if generate_followups:
        generate_followup_tasks(run, evidence_root=evidence_root, audit=audit)

    if settings.llm_critic_enabled:
        verdicts = llm_adversarial_review(verdicts, settings=settings)
        run_tier2_judge(run, settings=settings, evidence_root=evidence_root, audit=audit)
    return verdicts


# G9 — gap detection + follow-up generation ----------------------------------------


def _covered_artifact_paths(run: RunPaths) -> set[str]:
    """Every evidence path already covered by a task contract's input_artifacts."""
    covered: set[str] = set()
    for path in sorted(run.tasks.glob("TASK-*.yaml")):
        contract = read_yaml_model(TaskContract, path)
        covered.update(ia.path for ia in contract.input_artifacts)
    return covered


def _max_task_number(run: RunPaths) -> int:
    """Highest TASK-NNN number under tasks/ (0 if none)."""
    numbers = []
    for path in run.tasks.glob("TASK-*.yaml"):
        stem = path.stem  # "TASK-001"
        try:
            numbers.append(int(stem.split("-")[1]))
        except (IndexError, ValueError):
            continue
    return max(numbers, default=0)


def detect_coverage_gaps(run: RunPaths) -> list[RoutedArtifact]:
    """Actionable manifest artifacts not covered by any task (a coverage gap, G9)."""
    if not run.evidence_manifest.is_file():
        return []
    manifest = EvidenceManifest.model_validate_json(
        run.evidence_manifest.read_text(encoding="utf-8")
    )
    covered = _covered_artifact_paths(run)
    return [a for a in route_manifest(manifest) if a.actionable and a.path not in covered]


def detect_derived_gaps(run: RunPaths) -> list[RoutedArtifact]:
    """Actionable DERIVED (carved/decompressed) artifacts not covered by any task (hth.2).

    Reads ``evidence/derived_artifacts.json`` and routes each derived file by its basename — but a
    ``decompress``-produced image (``DECOMP-`` id) is forced to ``memory_image`` because a ``.raw``
    suffix would otherwise route to ``disk_image``. The intake manifest is never consulted/mutated.
    """
    covered = _covered_artifact_paths(run)
    gaps: list[RoutedArtifact] = []
    for rec in read_derived(run.root):
        if rec.derived_sha256 is None or rec.derived_path in covered:
            continue
        force: FineFamily | None = (
            "memory_image" if rec.tool_call_id.startswith("DECOMP-") else None
        )
        art = route_path(rec.derived_path, rec.derived_sha256, force_family=force)
        if art.actionable:
            gaps.append(art)
    return gaps


def _write_followup_task(
    run: RunPaths,
    arts: RoutedArtifact | list[RoutedArtifact],
    *,
    n: int,
    origin: ArtifactOrigin,
    reason: FollowupReason,
    evidence_root: Path | str | None,
    audit: FilteringBoundLogger,
) -> Path:
    """Mint TASK-{n:03d} for a gap artifact GROUP: write its contract + FollowupRecord, then log."""
    group = [arts] if isinstance(arts, RoutedArtifact) else list(arts)
    rep = group[0]
    task_id = f"TASK-{n:03d}"
    contract = executor_contract(task_id, group, origin=origin)
    target = safe_write_path(run.root, f"tasks/{task_id}.yaml", evidence_root=evidence_root)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(dump_yaml_model(contract), encoding="utf-8")
    append_followup(
        run.root,
        FollowupRecord(
            followup_id=next_followup_id(run.root),
            task_id=task_id,
            reason=reason,
            artifact=rep.path,
            family=rep.family,
            tool=rep.tool,
            created_utc=_now(),
        ),
        evidence_root=evidence_root,
    )
    log_event(
        audit,
        "followup_task_created",
        task_id=task_id,
        artifact=rep.path,
        gap=reason,
        artifacts=len(group),
    )
    return target


def generate_followup_tasks(
    run: RunPaths, *, evidence_root: Path | str | None, audit: FilteringBoundLogger
) -> list[Path]:
    """Create one follow-up task per coverage gap (manifest) AND per derived gap (hth.2).

    Idempotent — each new task's input path covers its gap, so a second pass finds none.
    """
    written: list[Path] = []
    n = _max_task_number(run)
    for group in group_actionable(detect_coverage_gaps(run)):
        n += 1
        written.append(
            _write_followup_task(
                run,
                group,
                n=n,
                origin="evidence",
                reason="coverage_gap",
                evidence_root=evidence_root,
                audit=audit,
            )
        )
    for group in group_actionable(detect_derived_gaps(run)):
        n += 1
        written.append(
            _write_followup_task(
                run,
                group,
                n=n,
                origin="derived",
                reason="derived_gap",
                evidence_root=evidence_root,
                audit=audit,
            )
        )
    return written


def ingest_derived(
    run: RunPaths,
    *,
    evidence_root: Path | str | None = None,
    audit: FilteringBoundLogger | None = None,
) -> list[Path]:
    """Explicit hth.2 primitive — create a derived task per uncovered actionable derived artifact.

    Same effect as the G9 derived-gap path, runnable on demand (the ``ingest-derived`` CLI) before
    the first critique. Idempotent; never touches ``evidence_manifest.json``.
    """
    log = audit or open_orchestration_log(run.orchestration_events, run.run_id)
    written: list[Path] = []
    n = _max_task_number(run)
    for group in group_actionable(detect_derived_gaps(run)):
        n += 1
        written.append(
            _write_followup_task(
                run,
                group,
                n=n,
                origin="derived",
                reason="derived_gap",
                evidence_root=evidence_root,
                audit=log,
            )
        )
    _ensure_dispatchable_plan(run, created=len(written))
    return written


def _ensure_dispatchable_plan(run: RunPaths, *, created: int) -> None:
    """Write a minimal InvestigationPlan if none exists, so the derived tasks are dispatchable.

    The staged manual flow (``extract-artifacts`` → ``ingest-derived`` → ``dispatch``) never runs
    ``plan``, so ``context/investigation_plan.yaml`` is absent and ``dispatch_run`` — which reads it
    only to check ``review_only`` — fails closed. The derived tasks already live in ``tasks/``; this
    records a non-review-only plan (empty step graph) so they can be dispatched. The ``plan`` /
    high-level engine paths are unaffected (the file already exists there, so this is a no-op).
    """
    if run.investigation_plan.exists():
        return
    manifest = EvidenceManifest.model_validate_json(
        run.evidence_manifest.read_text(encoding="utf-8")
    )
    plan = InvestigationPlan(
        plan_id=f"{run.run_id}-derived",
        case_id=manifest.case_id,
        template="derived-ingest",
        review_only=False,
        artifact_count=created,
        steps=[],
    )
    target = safe_write_path(run.root, "context/investigation_plan.yaml")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(dump_yaml_model(plan), encoding="utf-8")


def _record_corroboration_gaps(
    run: RunPaths,
    claims: list[Claim],
    *,
    evidence_root: Path | str | None,
    audit: FilteringBoundLogger,
) -> None:
    """Label high-risk single-source claims as needing corroboration (G9; never dropped)."""
    for claim in claims:
        high_risk = bool(_SEVERITY.search(claim.claim))
        if claim.status == "confirmed" and high_risk and len(claim.supporting_evidence_refs) <= 1:
            append_followup(
                run.root,
                FollowupRecord(
                    followup_id=next_followup_id(run.root),
                    task_id=claim.task_id,
                    reason="corroboration_gap",
                    artifact=claim.source_artifact or "",
                    family=claim.evidence_type,
                    origin_claim_id=claim.claim_id,
                    created_utc=_now(),
                ),
                evidence_root=evidence_root,
            )
            log_event(
                audit, "corroboration_gap_detected", task_id=claim.task_id, claim_id=claim.claim_id
            )


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
    """Layer-2 seam (G8): the Tier-1 verdicts are AUTHORITATIVE and returned unchanged.

    The advisory Tier-2 work (which may lower confidence / suggest corroboration / annotate, but
    NEVER promote) is done by :func:`run_tier2_judge` as logged side effects — it does not alter
    the deterministic verdicts.
    """
    return verdicts


# Closed verdict vocabulary the Tier-2 judge may return (advisory only — never promotes).
_TIER2_VERDICTS = frozenset({"ok", "overbroad", "low_confidence", "needs_corroboration"})


def _tier2_prompt(claims: list[Claim], objective: str | None) -> str:
    rows = "\n".join(
        f"- {c.claim_id} [{c.status}, confidence {c.confidence}] {c.claim}" for c in claims
    )
    obj = f"Investigation objective: {objective}\n\n" if objective else ""
    return (
        "You are an adversarial DFIR review judge. Below are EVIDENCE-ANCHORED findings a "
        "deterministic critic already accepted. You may ONLY flag concerns — you cannot add facts, "
        "add citations, raise confidence, or promote anything.\n\n" + obj + rows + "\n\n"
        "Respond with ONLY a JSON object (no prose):\n"
        '{"judgements": [{"claim_id": "<exact id above>", '
        '"verdict": "ok|overbroad|low_confidence|needs_corroboration", '
        '"note": "<short reason>", "suggested_confidence": 0.0-1.0}]}\n'
        "Use ONLY claim_ids from the list; omit suggested_confidence unless lowering it."
    )


def _append_tier2_judgement(
    run: RunPaths, payload: dict[str, object], evidence_root: Path | str | None
) -> None:
    target = safe_write_path(
        run.root, Path("audit") / "tier2_judgements.jsonl", evidence_root=evidence_root
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8", newline="\n") as out:
        out.write(json.dumps(payload, default=str) + "\n")


def run_tier2_judge(
    run: RunPaths,
    *,
    settings: SiftmeshSettings,
    evidence_root: Path | str | None,
    audit: FilteringBoundLogger,
) -> int:
    """Advisory Tier-2 LLM judge over the PROMOTED claims (G8). Returns judgements acted on.

    STRICTLY advisory: it may lower a claim's confidence (a logged ``confidence_change``), raise a
    corroboration follow-up, or annotate uncertainty (``tier2_judgements.jsonl``) — it NEVER
    promotes, adds, removes, or up-weights a claim (Tier-1 is the sole promoter). Fails soft: a
    missing agent / unparseable output / fabricated claim-ref produces no change.
    """
    promoted = [c for c in read_claims(run.root) if c.status in ("confirmed", "inferred")]
    if not promoted:
        return 0
    manifest = (
        EvidenceManifest.model_validate_json(run.evidence_manifest.read_text(encoding="utf-8"))
        if run.evidence_manifest.is_file()
        else None
    )
    objective = manifest.incident_objective if manifest else None
    text = invoke_claude_text(_tier2_prompt(promoted, objective), settings)
    if not text:
        return 0
    try:
        parsed = json.loads(text)
        judgements = parsed.get("judgements", []) if isinstance(parsed, dict) else []
    except (json.JSONDecodeError, ValueError):
        return 0
    by_id = {c.claim_id: c for c in promoted}
    acted = 0
    for j in judgements:
        if not isinstance(j, dict):
            continue
        cid = j.get("claim_id")
        verdict = j.get("verdict")
        if not isinstance(cid, str) or verdict not in _TIER2_VERDICTS:
            continue
        claim = by_id.get(cid)  # ignore fabricated / unknown ids (never act on them)
        if claim is None:
            continue
        sugg = j.get("suggested_confidence")
        _append_tier2_judgement(
            run,
            {
                "claim_id": cid,
                "verdict": verdict,
                "note": str(j.get("note", ""))[:300],
                "suggested_confidence": sugg,
            },
            evidence_root,
        )
        if (
            verdict in ("overbroad", "low_confidence")
            and isinstance(sugg, int | float)
            and 0.0 <= float(sugg) < claim.confidence  # may ONLY lower, never raise
        ):
            append_confidence_change(
                run.root,
                ConfidenceChange(
                    change_id=next_confidence_change_id(run.root),
                    claim_id=claim.claim_id,
                    task_id=claim.task_id,
                    from_confidence=claim.confidence,
                    to_confidence=round(float(sugg), 4),
                    reason=f"tier2 advisory ({verdict}): {str(j.get('note', ''))[:120]}",
                    changed_utc=_now(),
                ),
                evidence_root=evidence_root,
            )
        elif verdict == "needs_corroboration":
            append_followup(
                run.root,
                FollowupRecord(
                    followup_id=next_followup_id(run.root),
                    task_id=claim.task_id,
                    reason="corroboration_gap",
                    artifact=claim.source_artifact or "",
                    family=claim.evidence_type,
                    origin_claim_id=claim.claim_id,
                    created_utc=_now(),
                ),
                evidence_root=evidence_root,
            )
        acted += 1
    log_event(audit, "tier2_judge_complete", judgements=acted)
    return acted
