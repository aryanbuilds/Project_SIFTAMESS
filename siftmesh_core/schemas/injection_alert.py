"""Prompt-injection alert (Epic F, F3) — evidence that looks like an instruction.

When the spotlight scanner flags injection-like content in an evidence row or in a
live agent's returned reasoning, an :class:`InjectionAlert` is appended to
``claims/injection_alerts.jsonl``. In Epic F the alert is *logged only* — it never
changes control flow (criterion 4: "injection changes nothing"). The downgrade /
human-review consequence is wired by the critic in Epic G.
"""

from __future__ import annotations

from siftmesh_core.schemas._base import StrictModel, UtcDateTime


class InjectionAlert(StrictModel):
    """One prompt-injection detection (logged, not acted upon, in Epic F)."""

    alert_id: str  # deterministic ALERT-NNN from ledger length
    source: str  # "evidence_row" | "agent_result" | ...
    signature: str  # which scanner rule fired
    snippet: str  # the matched text, datamarked + truncated
    detected_utc: UtcDateTime
    task_id: str | None = None
    source_artifact: str | None = None
    requires_human_review: bool = True
