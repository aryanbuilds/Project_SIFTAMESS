"""Static MITRE ATT&CK lookup (J3 support) — evidence_type → technique, degrade-safe.

A small committed map (``attack_map.json``, CC-BY-4.0) keyed by the claim ``evidence_type``. Unknown
types return ``None`` (the report renders "(unmapped)" + lists them under LIMITATIONS) — a new tool
emitting a new evidence_type can never raise a KeyError. PowerShell script-block claims
(``windows_event_log`` whose text references EventID 4104/4103) are refined to T1059.001.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from siftmesh_core.schemas.claim import Claim

_MAP_PATH = Path(__file__).parent / "attack_map.json"


@dataclass(frozen=True)
class AttackEntry:
    """One ATT&CK mapping row."""

    tactic: str
    technique: str
    subtechnique: str | None
    name: str
    url: str

    @property
    def id_display(self) -> str:
        return self.subtechnique or self.technique


@lru_cache(maxsize=1)
def _raw_map() -> dict[str, dict[str, str] | None]:
    data = json.loads(_MAP_PATH.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_")}


def attack_attribution() -> str:
    """The license/source note for the dataset-documentation + limitations sections."""
    meta = json.loads(_MAP_PATH.read_text(encoding="utf-8")).get("_meta", {})
    return f"{meta.get('source', 'MITRE ATT&CK')} ({meta.get('license', 'CC-BY-4.0')})"


def lookup(evidence_type: str) -> AttackEntry | None:
    """Map a claim ``evidence_type`` to an :class:`AttackEntry`, or ``None`` if unmapped."""
    entry = _raw_map().get(evidence_type)
    if not entry:
        return None
    return AttackEntry(
        tactic=entry["tactic"],
        technique=entry["technique"],
        subtechnique=entry.get("subtechnique"),
        name=entry["name"],
        url=entry["url"],
    )


def lookup_for_claim(claim: Claim) -> AttackEntry | None:
    """Per-claim mapping with a deterministic PowerShell refinement for script-block events."""
    base = lookup(claim.evidence_type)
    if claim.evidence_type == "windows_event_log" and (
        "4104" in claim.claim or "4103" in claim.claim
    ):
        return lookup("evtx_powershell_event") or base
    return base
