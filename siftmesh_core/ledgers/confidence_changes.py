"""Confidence-change ledger (Epic G, G3) — audited claim downgrades.

Appends to ``claims/confidence_changes.jsonl`` (append-only; the original claim line
is never mutated — a reader joins claim + confidence_changes). ``next_confidence_change_id``
mints a deterministic ``CONF-NNN``.
"""

from __future__ import annotations

from pathlib import Path

from siftmesh_core.ledgers.jsonl_ledger import append_record, read_records
from siftmesh_core.schemas.critic_records import ConfidenceChange

_CONFIDENCE_CHANGES = Path("claims") / "confidence_changes.jsonl"


def next_confidence_change_id(run_root: Path | str) -> str:
    """Return the next ``CONF-NNN`` id from the current ledger length."""
    return f"CONF-{len(read_confidence_changes(run_root)) + 1:03d}"


def append_confidence_change(
    run_root: Path | str,
    change: ConfidenceChange,
    *,
    evidence_root: Path | str | None = None,
) -> Path:
    """Append one confidence change to ``claims/confidence_changes.jsonl``."""
    return append_record(run_root, _CONFIDENCE_CHANGES, change, evidence_root=evidence_root)


def read_confidence_changes(run_root: Path | str) -> list[ConfidenceChange]:
    """Read all confidence changes for a run."""
    return list(read_records(Path(run_root) / _CONFIDENCE_CHANGES, ConfidenceChange))
