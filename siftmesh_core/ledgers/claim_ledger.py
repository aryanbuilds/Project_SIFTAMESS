"""Claim ledger (C7): route each claim to the correct run-dir ledger by status.

Confirmed / inferred / contradicted claims land in ``claims/claim_ledger.jsonl``;
``unsupported`` claims land in ``claims/unsupported_claims.jsonl`` — so an
unsupported assertion is logged but kept out of the findings ledger by
construction ("log, don't delete, never report as fact"). Built on the generic
validate-before-write JSONL ledger.
"""

from __future__ import annotations

from pathlib import Path

from siftmesh_core.ledgers.jsonl_ledger import append_record, read_records
from siftmesh_core.schemas.claim import Claim

_CLAIM_LEDGER = Path("claims") / "claim_ledger.jsonl"
_UNSUPPORTED_LEDGER = Path("claims") / "unsupported_claims.jsonl"


def append_claim(
    run_root: Path | str,
    claim: Claim,
    *,
    evidence_root: Path | str | None = None,
) -> Path:
    """Append a claim to the findings or unsupported ledger based on its status."""
    rel = _UNSUPPORTED_LEDGER if claim.status == "unsupported" else _CLAIM_LEDGER
    return append_record(run_root, rel, claim, evidence_root=evidence_root)


def read_claims(run_root: Path | str) -> list[Claim]:
    """Read confirmed/inferred/contradicted claims from the findings ledger."""
    return list(read_records(Path(run_root) / _CLAIM_LEDGER, Claim))


def read_unsupported_claims(run_root: Path | str) -> list[Claim]:
    """Read the explicit ``unsupported`` claims ledger."""
    return list(read_records(Path(run_root) / _UNSUPPORTED_LEDGER, Claim))
