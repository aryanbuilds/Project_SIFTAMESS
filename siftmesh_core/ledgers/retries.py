"""Retry ledger (Epic G, G5) - self-correction retries (tightened-contract re-dispatch).

Appends to ``audit/retries.jsonl``; ``next_retry_id`` mints a deterministic ``RETRY-NNN``.
"""

from __future__ import annotations

from pathlib import Path

from siftmesh_core.ledgers.jsonl_ledger import append_record, read_records
from siftmesh_core.schemas.critic_records import RetryRecord

_RETRIES = Path("audit") / "retries.jsonl"


def next_retry_id(run_root: Path | str) -> str:
    """Return the next ``RETRY-NNN`` id from the current ledger length."""
    return f"RETRY-{len(read_retries(run_root)) + 1:03d}"


def append_retry(
    run_root: Path | str,
    record: RetryRecord,
    *,
    evidence_root: Path | str | None = None,
) -> Path:
    """Append one retry record to ``audit/retries.jsonl``."""
    return append_record(run_root, _RETRIES, record, evidence_root=evidence_root)


def read_retries(run_root: Path | str) -> list[RetryRecord]:
    """Read all retry records for a run."""
    return list(read_records(Path(run_root) / _RETRIES, RetryRecord))
