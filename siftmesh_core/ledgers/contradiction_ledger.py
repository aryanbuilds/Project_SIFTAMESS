"""Contradiction ledger (Epic G, G3) - claims that deterministically disagree.

Appends to ``claims/contradiction_ledger.jsonl``; ``next_contradiction_id`` mints a
deterministic ``CONTRA-NNN``.
"""

from __future__ import annotations

from pathlib import Path

from siftmesh_core.ledgers.jsonl_ledger import append_record, read_records
from siftmesh_core.schemas.critic_records import ContradictionRecord

_CONTRADICTIONS = Path("claims") / "contradiction_ledger.jsonl"


def next_contradiction_id(run_root: Path | str) -> str:
    """Return the next ``CONTRA-NNN`` id from the current ledger length."""
    return f"CONTRA-{len(read_contradictions(run_root)) + 1:03d}"


def append_contradiction(
    run_root: Path | str,
    record: ContradictionRecord,
    *,
    evidence_root: Path | str | None = None,
) -> Path:
    """Append one contradiction record to ``claims/contradiction_ledger.jsonl``."""
    return append_record(run_root, _CONTRADICTIONS, record, evidence_root=evidence_root)


def read_contradictions(run_root: Path | str) -> list[ContradictionRecord]:
    """Read all contradiction records for a run."""
    return list(read_records(Path(run_root) / _CONTRADICTIONS, ContradictionRecord))
