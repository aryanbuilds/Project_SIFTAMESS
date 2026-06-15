"""Parse a live agent's final message into a typed :class:`TaskResult` (Epic K, K3).

Both live adapters (Claude, OpenCode) drive their agent to investigate via the typed MCP tools and
respond with ONLY a JSON ``{"claims": [...]}`` payload, each claim citing the ``tool_call_id`` and
``source_sha256`` the MCP tool returned. This module turns that raw text into validated
:class:`~siftmesh_core.schemas.claim.Claim` objects, with two HARD honesty rules:

* **Never fabricate an anchor.** A claim the agent left under-anchored (missing ``source_sha256`` /
  ``tool_call_id``, or a malformed sha) is recorded as ``status="unsupported"`` - the explicit
  "agent said it, evidence is missing" record. The deterministic critic then rejects it and the
  orchestrator retries with feedback. That is the *genuine, emergent* self-correction loop - the
  adapter records exactly what the agent did and did not anchor; it does not rig the outcome.
* **Unparseable / empty output => ``retry_required``**, never a fabricated success.

The adapter does the bookkeeping the agent cannot know (``task_id``, the ``CLAIM-NNN`` id sequence);
everything that asserts something about the evidence comes from the agent + the real tool output.
"""

from __future__ import annotations

import json
import re
from datetime import datetime

from pydantic import ValidationError

from siftmesh_core.adapters.base import AdapterContext
from siftmesh_core.schemas.claim import Claim, validate_claim_evidence
from siftmesh_core.schemas.task import TaskContract
from siftmesh_core.schemas.task_result import TaskResult

_ANCHORED = ("confirmed", "inferred", "contradicted")
_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def _extract_json(text: str) -> dict[str, object] | None:
    """Best-effort: pull the agent's JSON object from its final message (fences/prose tolerated)."""
    for candidate in _json_candidates(text):
        try:
            obj = json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(obj, dict):
            return obj
    return None


def _json_candidates(text: str) -> list[str]:
    text = text.strip()
    candidates = [text]
    candidates += [m.group(1).strip() for m in _FENCE.finditer(text)]  # ```json ... ``` blocks
    start, end = text.find("{"), text.rfind("}")
    if 0 <= start < end:
        candidates.append(text[start : end + 1])  # outermost {...} span
    return candidates


def _clamp_confidence(value: object) -> float:
    try:
        conf = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.5
    return max(0.0, min(1.0, conf))


def _strlist(value: object) -> list[str]:
    return [str(x) for x in value] if isinstance(value, list) else []


def _normalize_claim(raw: dict[str, object], *, task_id: str, attempt: int, index: int) -> Claim:
    """One agent claim -> Claim; under-anchored or malformed => honest ``unsupported`` record.

    The ``claim_id`` is **attempt-scoped** (``…-A{attempt}-CLAIM-NNN``) so a corrected claim on a
    retry never collides with the rejected claim it replaces - otherwise the critic's promotion
    de-dup (``persisted_ids``) would silently drop the correction. The rejected attempt's record
    stays in its own ledger ("log, don't delete").
    """
    common: dict[str, object] = {
        "claim_id": f"{task_id}-A{attempt}-CLAIM-{index:03d}",
        "task_id": task_id,
        "claim": str(raw.get("claim", ""))[:2000],
        "confidence": _clamp_confidence(raw.get("confidence")),
        "evidence_type": str(raw.get("evidence_type") or "agent_assertion"),
        "source_artifact": raw.get("source_artifact"),
        "tool_name": raw.get("tool_name"),
        "tool_call_id": raw.get("tool_call_id"),
        "supporting_evidence_refs": _strlist(raw.get("supporting_evidence_refs")),
    }
    status = raw.get("status")
    if status in _ANCHORED and not validate_claim_evidence(
        raw
    ):  # agent anchored it -> trust + verify
        try:
            return Claim(**common, status=status, source_sha256=raw.get("source_sha256"))
        except ValidationError:
            pass  # malformed anchor (e.g. bad sha) -> fall through; never fabricate one
    return Claim(**common, status="unsupported")


def parse_agent_result(
    raw_text: str,
    *,
    contract: TaskContract,
    ctx: AdapterContext,
    adapter_id: str,
    started: datetime,
    ended: datetime,
) -> TaskResult:
    """Turn the agent's final message into a TaskResult; unparseable/empty => retry_required."""
    base: dict[str, object] = {
        "task_id": contract.task_id,
        "profile": ctx.requested_profile or adapter_id,
        "adapter": adapter_id,
        "attempt": ctx.attempt,
        "started_utc": started,
        "ended_utc": ended,
    }
    payload = _extract_json(raw_text)
    raw_claims = payload.get("claims") if payload else None
    if not isinstance(raw_claims, list):
        return TaskResult(
            **base,
            status="retry_required",
            retry_cause="agent_output_not_parseable_as_claims",
            errors=["agent did not emit a JSON {claims:[...]} payload"],
        )
    claims: list[Claim] = []
    tool_call_ids: list[str] = []
    for i, raw in enumerate(raw_claims, start=1):
        if not isinstance(raw, dict):
            continue
        claim = _normalize_claim(raw, task_id=contract.task_id, attempt=ctx.attempt, index=i)
        claims.append(claim)
        if claim.tool_call_id:
            tool_call_ids.append(claim.tool_call_id)
    if not claims:
        return TaskResult(
            **base,
            status="retry_required",
            retry_cause="agent_produced_no_claims",
            errors=["agent emitted an empty claims list"],
        )
    # status="success" = the adapter captured the agent's output; the CRITIC governs truth: an
    # under-anchored claim landed as 'unsupported' and the critic will drive a retry (the loop).
    return TaskResult(
        **base,
        status="success",
        claims=claims,
        tool_call_ids=tool_call_ids,
    )
