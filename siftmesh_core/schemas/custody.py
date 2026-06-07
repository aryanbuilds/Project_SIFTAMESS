"""Chain-of-custody event schema (C10, pulled forward for Epic B's B9).

``CustodyEvent`` is the typed backbone of the custody ledger
(``evidence/custody_log.jsonl``) — the criterion-5 (audit) differentiator,
aligned to ISO 27037 / NIST SP 800-86 (auditability, repeatability,
reproducibility). Validate-before-write: a malformed event never persists.
Explicit non-goal: not court-admissible.
"""

from __future__ import annotations

from typing import Literal

from siftmesh_core.schemas._base import Sha256, StrictModel, UtcDateTime

CustodyEventType = Literal[
    "evidence_ingested",
    "source_rehash_verified",
    "tool_invoked",
    "derived_written",
    "custody_transfer",
]


class CustodyEvent(StrictModel):
    """One immutable chain-of-custody record."""

    event_type: CustodyEventType
    run_id: str
    artifact: str
    source_sha256: Sha256
    action: str
    actor: str
    tool_name: str
    tool_version: str
    parser_version: str | None = None
    start_time_utc: UtcDateTime
    end_time_utc: UtcDateTime
    result: str
