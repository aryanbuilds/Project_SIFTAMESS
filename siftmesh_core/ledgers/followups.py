"""Follow-up ledger (Epic G, G9) - coverage/corroboration gaps the critic raised.

Appends to ``audit/followups.jsonl``; ``next_followup_id`` mints a deterministic
``FOLLOWUP-NNN``.
"""

from __future__ import annotations

from pathlib import Path

from siftmesh_core.ledgers.jsonl_ledger import append_record, read_records
from siftmesh_core.schemas.critic_records import FollowupRecord

_FOLLOWUPS = Path("audit") / "followups.jsonl"


def next_followup_id(run_root: Path | str) -> str:
    """Return the next ``FOLLOWUP-NNN`` id from the current ledger length."""
    return f"FOLLOWUP-{len(read_followups(run_root)) + 1:03d}"


def append_followup(
    run_root: Path | str,
    record: FollowupRecord,
    *,
    evidence_root: Path | str | None = None,
) -> Path:
    """Append one follow-up record to ``audit/followups.jsonl``."""
    return append_record(run_root, _FOLLOWUPS, record, evidence_root=evidence_root)


def read_followups(run_root: Path | str) -> list[FollowupRecord]:
    """Read all follow-up records for a run."""
    return list(read_records(Path(run_root) / _FOLLOWUPS, FollowupRecord))
