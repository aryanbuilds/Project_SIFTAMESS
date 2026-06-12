"""Deterministic real-tool executor (Epic F, F2) — the floor.

Runs the contract's single allowlisted Epic-D tool over the real evidence and
derives **deterministic, evidence-anchored** Claims from the genuine tool output.
This is NOT a mock and NOT a ledger-replay (CLAUDE §2B): it executes the real tool
every time (over committed public fixtures in CI, over real evidence on a SIFT
host). It is the regression/replay floor and the no-keys demo path; the genuine
self-correction hero is the live agent (Epic G).

Tool calls are already audited by ``mcp_gateway.audit_exec.run_tool`` (it mints
``TOOL-NNN`` and writes ``tool_calls.jsonl``/custody/derived) — this module only
calls the tool fn, reads back the typed result, and turns its rows into Claims.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from siftmesh_core.adapters.base import AdapterContext, ExecutorAdapter, register
from siftmesh_core.adapters.spotlight import scan_injection
from siftmesh_core.ledgers.claim_ledger import append_claim
from siftmesh_core.ledgers.injection_alerts import append_injection_alert, next_alert_id
from siftmesh_core.mcp_gateway.tools.evtx_tools import parse_evtx_powershell, parse_evtx_security
from siftmesh_core.mcp_gateway.tools.image_tools import extract_artifacts_from_image
from siftmesh_core.mcp_gateway.tools.memory_tools import analyze_memory
from siftmesh_core.mcp_gateway.tools.mft_tools import parse_mft_filesystem
from siftmesh_core.mcp_gateway.tools.prefetch_tools import analyze_prefetch
from siftmesh_core.mcp_gateway.tools.registry_tools import extract_registry_run_keys
from siftmesh_core.mcp_gateway.tools.timeline_tools import build_timeline
from siftmesh_core.orchestrator.artifact_router import timeline_kind_for
from siftmesh_core.schemas.claim import Claim
from siftmesh_core.schemas.injection_alert import InjectionAlert
from siftmesh_core.schemas.task import TaskContract
from siftmesh_core.schemas.task_result import TaskResult
from siftmesh_core.schemas.tool_result import ToolResult

# High-signal Windows event IDs the executor surfaces as individual claims.
_SECURITY_IDS = {
    4624: "successful logon",
    4625: "failed logon",
    4672: "special privileges assigned",
    4688: "process created",
    4720: "user account created",
    4726: "user account deleted",
}
_POWERSHELL_IDS = {4103: "module logging", 4104: "script-block logging"}


def _claim(
    result: ToolResult,
    task_id: str,
    n: int,
    *,
    status: str,
    text: str,
    evidence_type: str,
    confidence: float,
    requires_human_review: bool = False,
) -> Claim:
    """Build one evidence-anchored Claim from a tool result (fixed, deterministic)."""
    return Claim(
        claim_id=f"{task_id}-CLAIM-{n:03d}",
        task_id=task_id,
        status=status,
        claim=text,
        confidence=confidence,
        evidence_type=evidence_type,
        source_artifact=result.source_artifact,
        source_sha256=result.source_sha256,
        tool_name=result.tool_name,
        tool_call_id=result.tool_call_id,
        timestamp_utc=result.end_time_utc,
        supporting_evidence_refs=[result.tool_call_id],
        requires_human_review=requires_human_review,
    )


def _claims_evtx(result: Any, task_id: str, *, notable: dict[int, str], label: str) -> list[Claim]:
    events: list[dict[str, Any]] = list(result.events)
    if not events:
        return [
            _claim(
                result,
                task_id,
                1,
                status="inferred",
                text=f"No {label} events parsed from the artifact.",
                evidence_type="windows_event_log",
                confidence=0.5,
            )
        ]
    claims = [
        _claim(
            result,
            task_id,
            1,
            status="confirmed",
            text=f"Parsed {result.event_count} {label} event(s).",
            evidence_type="windows_event_log",
            confidence=0.95,
        )
    ]
    n = 1
    for idx, ev in enumerate(events, start=1):
        eid = ev.get("event_id")
        if eid in notable:
            n += 1
            claims.append(
                _claim(
                    result,
                    task_id,
                    n,
                    status="confirmed",
                    text=f"{label} EventID {eid} ({notable[eid]}) observed (event #{idx}).",
                    evidence_type="windows_event_log",
                    confidence=0.9,
                )
            )
    return claims


def _claims_prefetch(result: Any, task_id: str) -> list[Claim]:
    claims = [
        _claim(
            result,
            task_id,
            1,
            status="confirmed",
            text=f"{result.executable_filename} executed {result.run_count} time(s).",
            evidence_type="program_execution",
            confidence=0.9,
        )
    ]
    if result.last_run_times:
        claims.append(
            _claim(
                result,
                task_id,
                2,
                status="inferred",
                text=f"{len(result.last_run_times)} execution timestamp(s) recorded.",
                evidence_type="program_execution",
                confidence=0.7,
            )
        )
    return claims


def _claims_registry(result: Any, task_id: str) -> list[Claim]:
    claims = [
        _claim(
            result,
            task_id,
            1,
            status="confirmed",
            text=f"{result.run_key_count} autostart Run/RunOnce value(s) found.",
            evidence_type="registry_autostart",
            confidence=0.85,
        )
    ]
    for n, row in enumerate(result.run_keys, start=2):
        name = row.get("name", "?")
        key_path = row.get("key_path", "")
        claims.append(
            _claim(
                result,
                task_id,
                n,
                status="confirmed",
                text=f"Autostart Run key {name!r} present under {key_path}.",
                evidence_type="registry_autostart",
                confidence=0.85,
            )
        )
    return claims


def _claims_mft(result: Any, task_id: str) -> list[Claim]:
    return [
        _claim(
            result,
            task_id,
            1,
            status="confirmed",
            text=f"$MFT parsed: {result.entry_count} filesystem entries "
            f"({result.file_count} files, {result.directory_count} directories).",
            evidence_type="filesystem_mft",
            confidence=0.9,
        )
    ]


def _claims_timeline(result: Any, task_id: str) -> list[Claim]:
    return [
        _claim(
            result,
            task_id,
            1,
            status="inferred",
            text=f"Unified timeline built: {result.event_count} events across "
            f"{len(result.sources)} source(s).",
            evidence_type="timeline",
            confidence=0.6,
        )
    ]


def _claims_image(result: Any, task_id: str) -> list[Claim]:
    return [
        _claim(
            result,
            task_id,
            1,
            status="confirmed",
            text=f"Extracted {result.extracted_count} curated artifact(s) from the disk image.",
            evidence_type="image_extraction",
            confidence=0.8,
        )
    ]


def _claims_memory(result: Any, task_id: str) -> list[Claim]:
    claims = [
        _claim(
            result,
            task_id,
            1,
            status="confirmed",
            text=f"Memory triage: {result.process_count} process(es), "
            f"{len(result.network)} network endpoint(s).",
            evidence_type="memory_analysis",
            confidence=0.8,
        )
    ]
    for n, row in enumerate(result.suspicious, start=2):
        pid = row.get("pid", "?")
        proc = row.get("process", "?")
        claims.append(
            _claim(
                result,
                task_id,
                n,
                status="inferred",
                text=f"Possible injected code in PID {pid} ({proc}).",
                evidence_type="memory_analysis",
                confidence=0.5,
                requires_human_review=True,
            )
        )
    return claims


def _input_root(c: TaskContract, ctx: AdapterContext) -> Path | str:
    """Root the first input resolves against: the run dir for a derived (carved/decompressed)
    artifact (hth.2), else the original evidence root."""
    if c.input_artifacts and c.input_artifacts[0].origin == "derived":
        return ctx.run.root
    return ctx.evidence_root


def _single_source_kwargs(c: TaskContract, ctx: AdapterContext) -> dict[str, Any]:
    return {
        "source_artifact": c.input_artifacts[0].path,
        "evidence_root": _input_root(c, ctx),
        "backend_mode": ctx.settings.backend_mode,
    }


def _image_kwargs(c: TaskContract, ctx: AdapterContext) -> dict[str, Any]:
    return {
        "image_artifact": c.input_artifacts[0].path,
        "evidence_root": _input_root(c, ctx),
        "keys": None,
        "backend_mode": "sift_lane",
    }


def _memory_kwargs(c: TaskContract, ctx: AdapterContext) -> dict[str, Any]:
    return {
        "memory_artifact": c.input_artifacts[0].path,
        "evidence_root": _input_root(c, ctx),
        "plugins": None,
        "vol_path": ctx.settings.vol_path,
        "symbol_dirs": ctx.settings.vol_symbol_dirs,
        # A real 19 GB dump needs minutes, not the 300 s default tool cap.
        "timeout": ctx.settings.heavy_tool_timeout_seconds,
        "backend_mode": "sift_lane",
    }


def _timeline_kwargs(c: TaskContract, ctx: AdapterContext) -> dict[str, Any]:
    inputs = []
    for art in c.input_artifacts:
        kind = timeline_kind_for(art.path)
        if kind is not None:
            inputs.append({"artifact": art.path, "kind": kind})
    return {
        "inputs": inputs,
        "evidence_root": ctx.evidence_root,
        "backend_mode": ctx.settings.backend_mode,
    }


# tool name -> (tool callable, kwargs builder, claim deriver)
_DISPATCH: dict[
    str,
    tuple[
        Callable[..., ToolResult],
        Callable[[TaskContract, AdapterContext], dict[str, Any]],
        Callable[[Any, str], list[Claim]],
    ],
] = {
    "parse_evtx_security": (
        parse_evtx_security,
        _single_source_kwargs,
        lambda r, t: _claims_evtx(r, t, notable=_SECURITY_IDS, label="Security"),
    ),
    "parse_evtx_powershell": (
        parse_evtx_powershell,
        _single_source_kwargs,
        lambda r, t: _claims_evtx(r, t, notable=_POWERSHELL_IDS, label="PowerShell"),
    ),
    "analyze_prefetch": (analyze_prefetch, _single_source_kwargs, _claims_prefetch),
    "extract_registry_run_keys": (
        extract_registry_run_keys,
        _single_source_kwargs,
        _claims_registry,
    ),
    "build_timeline": (build_timeline, _timeline_kwargs, _claims_timeline),
    "extract_artifacts_from_image": (extract_artifacts_from_image, _image_kwargs, _claims_image),
    "analyze_memory": (analyze_memory, _memory_kwargs, _claims_memory),
    "parse_mft_filesystem": (parse_mft_filesystem, _single_source_kwargs, _claims_mft),
}


def _evidence_rows(result: ToolResult) -> list[dict[str, Any]]:
    """Pull the untrusted row list off whichever result subclass attr carries it."""
    for attr in ("events", "run_keys", "processes", "cmdlines", "suspicious", "extracted", "files"):
        rows = getattr(result, attr, None)
        if rows:
            return list(rows)
    return []


def scan_and_log_rows(
    ctx: AdapterContext,
    *,
    task_id: str,
    source_artifact: str,
    rows: list[dict[str, Any]],
) -> int:
    """Scan evidence rows for injection signatures; log alerts. Returns alert count.

    Logged only — never changes the executor's output (criterion 4: injection
    changes nothing here; the consequence is Epic G).
    """
    text = json.dumps(rows, default=str)
    matches = scan_injection(text)
    for m in matches:
        append_injection_alert(
            ctx.run.root,
            InjectionAlert(
                alert_id=next_alert_id(ctx.run.root),
                source="evidence_row",
                signature=m.signature,
                snippet=m.snippet,
                detected_utc=datetime.now(UTC),
                task_id=task_id,
                source_artifact=source_artifact,
            ),
            evidence_root=ctx.evidence_root,
        )
    return len(matches)


# Single-source parse tools the floor runs once PER input artifact (per-family aggregation, bd
# 1xy6): one aggregated task → one audited tool call per .pf/hive/evtx, claims merged + renumbered.
# build_timeline (aggregates inputs itself) and image/memory (inherently single-source) stay 1-call.
_PER_ARTIFACT_TOOLS = frozenset(
    {
        "parse_evtx_security",
        "parse_evtx_powershell",
        "analyze_prefetch",
        "extract_registry_run_keys",
        "parse_mft_filesystem",
    }
)


@register
class DeterministicExecutor(ExecutorAdapter):
    """The real-tool floor: real Epic-D tools over real evidence → deterministic claims."""

    profile_id = "deterministic_executor"
    backend_label = "real"

    def _result(
        self,
        contract: TaskContract,
        ctx: AdapterContext,
        started: datetime,
        *,
        status: str,
        tool_call_ids: list[str] | None = None,
        claims: list[Claim] | None = None,
        errors: list[str] | None = None,
        retry_cause: str | None = None,
    ) -> TaskResult:
        return TaskResult(
            task_id=contract.task_id,
            profile=ctx.requested_profile or self.profile_id,
            adapter=self.profile_id,
            attempt=ctx.attempt,
            status=status,
            tool_call_ids=tool_call_ids or [],
            claims=claims or [],
            started_utc=started,
            ended_utc=datetime.now(UTC),
            errors=errors or [],
            retry_cause=retry_cause,
        )

    def _execute(self, contract: TaskContract, ctx: AdapterContext) -> TaskResult:
        started = datetime.now(UTC)
        tool = contract.allowed_tools[0] if contract.allowed_tools else ""
        if tool not in _DISPATCH:
            return self._result(
                contract, ctx, started, status="error", errors=[f"unsupported_tool:{tool}"]
            )
        fn, build_kwargs, derive_claims = _DISPATCH[tool]
        if tool in _PER_ARTIFACT_TOOLS and len(contract.input_artifacts) > 1:
            return self._run_per_artifact(contract, ctx, fn, derive_claims, started)

        result = fn(ctx.run.root, **build_kwargs(contract, ctx))  # audited by run_tool
        if result.status != "success":
            return self._result(
                contract,
                ctx,
                started,
                status="retry_required",
                tool_call_ids=[result.tool_call_id],
                errors=[result.error_code or "tool_error"],
                retry_cause="recoverable_tool_error",
            )
        scan_and_log_rows(
            ctx,
            task_id=contract.task_id,
            source_artifact=result.source_artifact,
            rows=_evidence_rows(result),
        )
        claims = derive_claims(result, contract.task_id)
        for c in claims:
            append_claim(ctx.run.root, c, evidence_root=ctx.evidence_root)
        return self._result(
            contract,
            ctx,
            started,
            status="success",
            tool_call_ids=[result.tool_call_id],
            claims=claims,
        )

    def _run_per_artifact(
        self,
        contract: TaskContract,
        ctx: AdapterContext,
        fn: Callable[..., ToolResult],
        derive_claims: Callable[[Any, str], list[Claim]],
        started: datetime,
    ) -> TaskResult:
        """Run a single-source tool over EVERY input artifact; merge + renumber claims (bd 1xy6).

        One audited ``run_tool`` call per artifact (per-artifact provenance preserved in
        tool_calls.jsonl). Partial failures are recorded but never fatal; the task succeeds if any
        artifact parsed, else retry_required.
        """
        all_claims: list[Claim] = []
        tool_call_ids: list[str] = []
        errors: list[str] = []
        any_ok = False
        for art in contract.input_artifacts:
            root = ctx.run.root if art.origin == "derived" else ctx.evidence_root
            result = fn(
                ctx.run.root,
                source_artifact=art.path,
                evidence_root=root,
                backend_mode=ctx.settings.backend_mode,
            )
            tool_call_ids.append(result.tool_call_id)
            if result.status != "success":
                errors.append(f"{art.path}:{result.error_code or 'tool_error'}")
                continue
            any_ok = True
            scan_and_log_rows(
                ctx,
                task_id=contract.task_id,
                source_artifact=result.source_artifact,
                rows=_evidence_rows(result),
            )
            all_claims.extend(derive_claims(result, contract.task_id))
        if not any_ok:
            return self._result(
                contract,
                ctx,
                started,
                status="retry_required",
                tool_call_ids=tool_call_ids,
                errors=errors or ["tool_error"],
                retry_cause="recoverable_tool_error",
            )
        # Renumber claim_ids to stay unique across the aggregated artifacts (anchors unchanged).
        claims = [
            c.model_copy(update={"claim_id": f"{contract.task_id}-CLAIM-{i:03d}"})
            for i, c in enumerate(all_claims, start=1)
        ]
        for c in claims:
            append_claim(ctx.run.root, c, evidence_root=ctx.evidence_root)
        return self._result(
            contract,
            ctx,
            started,
            status="success",
            tool_call_ids=tool_call_ids,
            claims=claims,
            errors=errors,
        )
