"""Critic-verdict ledger (Epic G, G1) — one CriticVerdict per critiqued task.

Appends to ``audit/critic_verdicts.jsonl`` on the generic validate-before-write
JSONL ledger; ``next_verdict_id`` mints a deterministic ``VERDICT-NNN``.
"""

from __future__ import annotations

from pathlib import Path

from siftmesh_core.ledgers.jsonl_ledger import append_record, read_records
from siftmesh_core.schemas.audit import CriticVerdict

_CRITIC_VERDICTS = Path("audit") / "critic_verdicts.jsonl"


def next_verdict_id(run_root: Path | str) -> str:
    """Return the next ``VERDICT-NNN`` id from the current ledger length."""
    return f"VERDICT-{len(read_critic_verdicts(run_root)) + 1:03d}"


def append_critic_verdict(
    run_root: Path | str,
    verdict: CriticVerdict,
    *,
    evidence_root: Path | str | None = None,
) -> Path:
    """Append one critic verdict to ``audit/critic_verdicts.jsonl``."""
    return append_record(run_root, _CRITIC_VERDICTS, verdict, evidence_root=evidence_root)


def read_critic_verdicts(run_root: Path | str) -> list[CriticVerdict]:
    """Read all critic verdicts for a run."""
    return list(read_records(Path(run_root) / _CRITIC_VERDICTS, CriticVerdict))
