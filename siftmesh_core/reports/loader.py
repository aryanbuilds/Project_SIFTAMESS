"""Report data-loader (J1) — one frozen, deterministic view over every run-dir ledger.

``load_report_view`` reads each ledger ONCE, validates it, stable-sorts it, and precomputes the
joins the generators need, returning one immutable :class:`ReportView`. It is a pure function of
the run-dir files (the "replayable audit" guarantee) with two reality-grounded rules:

* **Graceful-missing.** A missing ledger file → empty; a missing manifest / run_state → ``None`` +
  a ``load_errors`` note (a halted or discrete-command run still reports). Only absent
  manifest/run_state and ``read_records`` blank/corrupt lines are special-cased.
* **Corruption is surfaced, not hidden.** A corrupt JSONL line raises :class:`ReportLoadError`
  (``file:line``) by default. ``strict=False`` (``--tolerant``) drops only a *trailing* truncated
  line (crash-mid-write), recorded in ``load_errors``; an interior corrupt line always raises.

The view also enforces the hallucination firewall structurally: ``unsupported`` claims are reachable
ONLY via the ``unsupported`` field (the rejected appendix), never merged into the finding lists.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypeVar

from pydantic import ValidationError

from siftmesh_core.evidence.derived import DerivedArtifact, read_derived
from siftmesh_core.ledgers.jsonl_ledger import LedgerCorruptionError, read_records
from siftmesh_core.run_dir import RunPaths
from siftmesh_core.schemas._base import StrictModel
from siftmesh_core.schemas.agent_call import AgentCall
from siftmesh_core.schemas.audit import CriticVerdict
from siftmesh_core.schemas.claim import Claim
from siftmesh_core.schemas.critic_records import (
    ConfidenceChange,
    ContradictionRecord,
    FollowupRecord,
    RetryRecord,
)
from siftmesh_core.schemas.custody import CustodyEvent
from siftmesh_core.schemas.evidence import EvidenceManifest
from siftmesh_core.schemas.injection_alert import InjectionAlert
from siftmesh_core.schemas.run import RunState
from siftmesh_core.schemas.tool_result import ToolResult

ModelT = TypeVar("ModelT", bound=StrictModel)

# Cap on individually-rendered findings (a real disk image yields 400+); buckets summarize the rest.
# The tool-execution appendix is NEVER capped. Module constant => deterministic + reviewable.
MAX_DETAILED_FINDINGS = 50


class ReportLoadError(Exception):
    """A ledger could not be loaded for reporting (corrupt line, bad manifest, …)."""


@dataclass(frozen=True)
class OrchestrationEvent:
    """One structlog orchestration event (open vocabulary; parsed as a raw dict, not a schema)."""

    event: str
    timestamp: str  # ISO-8601 Z string as written by structlog (NOT a UtcDateTime field)
    lineno: int  # authoritative append order (the log has no sequence counter)
    run_id: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ReportView:
    """An immutable, stable-sorted snapshot of one run, ready for deterministic rendering."""

    run_id: str
    run_root: Path
    manifest: EvidenceManifest | None
    run_state: RunState | None
    # claims partitioned by status — unsupported is segregated by construction (firewall):
    confirmed: tuple[Claim, ...]
    inferred: tuple[Claim, ...]
    contradicted: tuple[Claim, ...]
    unsupported: tuple[Claim, ...]
    # raw ledgers (each stable-sorted):
    contradictions: tuple[ContradictionRecord, ...]
    confidence_changes: tuple[ConfidenceChange, ...]
    injection_alerts: tuple[InjectionAlert, ...]
    retries: tuple[RetryRecord, ...]
    followups: tuple[FollowupRecord, ...]
    verdicts: tuple[CriticVerdict, ...]
    tool_results: tuple[ToolResult, ...]
    agent_calls: tuple[AgentCall, ...]
    derived: tuple[DerivedArtifact, ...]
    custody: tuple[CustodyEvent, ...]
    events: tuple[OrchestrationEvent, ...]
    load_errors: tuple[str, ...]
    # precomputed joins (so templates stay logic-light + deterministic):
    confidence_by_claim_id: dict[str, tuple[float, float]]  # claim_id -> (original_from, final_to)
    verdict_by_task_id: dict[str, CriticVerdict]  # latest verdict per task
    failed_tool_call_ids: frozenset[str]
    claims_on_failed_tools: tuple[str, ...]
    findings_by_evidence_type: dict[str, int]
    findings_by_source_artifact: dict[str, int]
    high_signal_claims: tuple[Claim, ...]

    @property
    def has_execution(self) -> bool:
        """True if anything actually ran (claims, tools, or agent calls present)."""
        return bool(self.confirmed or self.inferred or self.tool_results or self.agent_calls)

    @property
    def verdict_tally(self) -> dict[str, int]:
        tally: Counter[str] = Counter(v.verdict for v in self.verdicts)
        return dict(sorted(tally.items()))


def load_report_view(
    run: RunPaths, *, evidence_root: Path | str | None = None, strict: bool = True
) -> ReportView:
    """Read every ledger once → a stable-sorted, immutable :class:`ReportView`."""
    errors: list[str] = []

    claims = _read_ledger(run.claim_ledger, Claim, strict=strict, errors=errors)
    unsupported = _read_ledger(run.unsupported_claims, Claim, strict=strict, errors=errors)
    contradictions = _read_ledger(
        run.contradiction_ledger, ContradictionRecord, strict=strict, errors=errors
    )
    conf_changes = _read_ledger(
        run.confidence_changes, ConfidenceChange, strict=strict, errors=errors
    )
    injections = _read_ledger(run.injection_alerts, InjectionAlert, strict=strict, errors=errors)
    retries = _read_ledger(run.retries, RetryRecord, strict=strict, errors=errors)
    followups = _read_ledger(run.followups, FollowupRecord, strict=strict, errors=errors)
    verdicts = _read_ledger(run.critic_verdicts, CriticVerdict, strict=strict, errors=errors)
    tools = _read_ledger(run.tool_calls, ToolResult, strict=strict, errors=errors)
    agents = _read_ledger(run.agent_calls, AgentCall, strict=strict, errors=errors)
    custody = _read_ledger(run.custody_log, CustodyEvent, strict=strict, errors=errors)
    events = _read_events(run.orchestration_events, strict=strict, errors=errors)
    derived = tuple(sorted(read_derived(run.root), key=lambda d: d.derived_path))

    manifest = _read_manifest(run, errors)
    run_state = _read_run_state(run, errors)

    confirmed = tuple(
        sorted((c for c in claims if c.status == "confirmed"), key=lambda c: c.claim_id)
    )
    inferred = tuple(
        sorted((c for c in claims if c.status == "inferred"), key=lambda c: c.claim_id)
    )
    contradicted = tuple(
        sorted((c for c in claims if c.status == "contradicted"), key=lambda c: c.claim_id)
    )
    unsupported_sorted = tuple(sorted(unsupported, key=lambda c: c.claim_id))

    findings = (*confirmed, *inferred, *contradicted)
    failed_tool_ids = frozenset(t.tool_call_id for t in tools if t.status != "success")
    claims_on_failed = tuple(
        sorted(c.claim_id for c in findings if c.tool_call_id and c.tool_call_id in failed_tool_ids)
    )

    return ReportView(
        run_id=run.run_id,
        run_root=run.root,
        manifest=manifest,
        run_state=run_state,
        confirmed=confirmed,
        inferred=inferred,
        contradicted=contradicted,
        unsupported=unsupported_sorted,
        contradictions=tuple(sorted(contradictions, key=lambda x: x.contradiction_id)),
        confidence_changes=tuple(sorted(conf_changes, key=lambda x: x.change_id)),
        injection_alerts=tuple(sorted(injections, key=lambda x: x.alert_id)),
        retries=tuple(sorted(retries, key=lambda x: x.retry_id)),
        followups=tuple(sorted(followups, key=lambda x: x.followup_id)),
        verdicts=tuple(sorted(verdicts, key=lambda v: (v.task_id or "", v.verdict_id or ""))),
        tool_results=tuple(sorted(tools, key=lambda t: t.tool_call_id)),
        agent_calls=tuple(sorted(agents, key=lambda a: a.agent_call_id)),
        derived=derived,
        custody=tuple(sorted(custody, key=lambda e: (e.start_time_utc, e.artifact, e.event_type))),
        events=tuple(sorted(events, key=lambda e: (e.timestamp, e.lineno))),
        load_errors=tuple(errors),
        confidence_by_claim_id=_confidence_joins(conf_changes),
        verdict_by_task_id=_latest_verdict_by_task(verdicts),
        failed_tool_call_ids=failed_tool_ids,
        claims_on_failed_tools=claims_on_failed,
        findings_by_evidence_type=_counts(findings, lambda c: c.evidence_type),
        findings_by_source_artifact=_counts(findings, lambda c: c.source_artifact or "(none)"),
        high_signal_claims=_rank_high_signal(confirmed, inferred),
    )


# ── reading helpers ───────────────────────────────────────────────────────────


def _read_ledger(
    path: Path, model_cls: type[ModelT], *, strict: bool, errors: list[str]
) -> list[ModelT]:
    """Strict: surface any corrupt line. Tolerant: drop only a trailing truncated line."""
    try:
        return list(read_records(path, model_cls))
    except LedgerCorruptionError as exc:
        if strict:
            raise ReportLoadError(str(exc)) from exc
        return _read_tolerant(path, model_cls, errors)


def _read_tolerant(path: Path, model_cls: type[ModelT], errors: list[str]) -> list[ModelT]:
    out: list[ModelT] = []
    nonempty = [(i, ln) for i, ln in enumerate(_lines(path), 1) if ln.strip()]
    for pos, (lineno, line) in enumerate(nonempty):
        try:
            out.append(model_cls.model_validate_json(line))
        except ValidationError as exc:
            if pos == len(nonempty) - 1:  # trailing truncated line (crash mid-write) -> drop
                errors.append(f"dropped truncated final line {lineno} of {path.name}")
            else:
                raise ReportLoadError(f"{path}:{lineno}: {exc}") from exc
    return out


def _read_events(path: Path, *, strict: bool, errors: list[str]) -> list[OrchestrationEvent]:
    """orchestration_events.jsonl: open-vocabulary structlog dicts (not a StrictModel)."""
    nonempty = [(i, ln) for i, ln in enumerate(_lines(path), 1) if ln.strip()]
    out: list[OrchestrationEvent] = []
    for pos, (lineno, line) in enumerate(nonempty):
        try:
            record = json.loads(line)
        except (json.JSONDecodeError, ValueError) as exc:
            if not strict and pos == len(nonempty) - 1:
                errors.append(f"dropped truncated final line {lineno} of {path.name}")
                continue
            raise ReportLoadError(f"{path}:{lineno}: {exc}") from exc
        if not isinstance(record, dict):
            raise ReportLoadError(f"{path}:{lineno}: orchestration event is not a JSON object")
        reserved = {"event", "timestamp", "run_id", "level"}
        out.append(
            OrchestrationEvent(
                event=str(record.get("event", "")),
                timestamp=str(record.get("timestamp", "")),
                lineno=lineno,
                run_id=record.get("run_id"),
                extra={k: v for k, v in record.items() if k not in reserved},
            )
        )
    return out


def _lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines() if path.is_file() else []


def _read_manifest(run: RunPaths, errors: list[str]) -> EvidenceManifest | None:
    if not run.evidence_manifest.is_file():
        errors.append("no evidence_manifest.json (run not sealed)")
        return None
    try:
        return EvidenceManifest.model_validate_json(
            run.evidence_manifest.read_text(encoding="utf-8")
        )
    except ValidationError as exc:
        raise ReportLoadError(f"{run.evidence_manifest}: {exc}") from exc


def _read_run_state(run: RunPaths, errors: list[str]) -> RunState | None:
    if not run.run_state.is_file():
        errors.append("no run_state.json (run driven by discrete commands; engine snapshot absent)")
        return None
    try:
        return RunState.model_validate_json(run.run_state.read_text(encoding="utf-8"))
    except ValidationError as exc:
        raise ReportLoadError(f"{run.run_state}: {exc}") from exc


# ── join/aggregate helpers ─────────────────────────────────────────────────────


def _confidence_joins(changes: list[ConfidenceChange]) -> dict[str, tuple[float, float]]:
    """claim_id -> (original from-confidence, final to-confidence), deterministic over a chain."""
    by_claim: dict[str, list[ConfidenceChange]] = defaultdict(list)
    for ch in changes:
        by_claim[ch.claim_id].append(ch)
    result: dict[str, tuple[float, float]] = {}
    for claim_id, chain in by_claim.items():
        chain.sort(key=lambda c: c.change_id)
        result[claim_id] = (chain[0].from_confidence, chain[-1].to_confidence)
    return dict(sorted(result.items()))


def _latest_verdict_by_task(verdicts: list[CriticVerdict]) -> dict[str, CriticVerdict]:
    ordered = sorted(verdicts, key=lambda v: (v.task_id or "", v.verdict_id or ""))
    latest: dict[str, CriticVerdict] = {}
    for v in ordered:
        if v.task_id:
            latest[v.task_id] = v  # last by verdict_id wins
    return dict(sorted(latest.items()))


def _counts(claims: tuple[Claim, ...], key: Any) -> dict[str, int]:
    return dict(sorted(Counter(key(c) for c in claims).items()))


def _rank_high_signal(
    confirmed: tuple[Claim, ...], inferred: tuple[Claim, ...]
) -> tuple[Claim, ...]:
    """Confirmed+inferred ranked human-review-first, then confidence, then id; capped."""
    ranked = sorted(
        (*confirmed, *inferred),
        key=lambda c: (not c.requires_human_review, -c.confidence, c.claim_id),
    )
    return tuple(ranked[:MAX_DETAILED_FINDINGS])
