"""Prompt-injection alert ledger (Epic F, F3).

Appends one :class:`InjectionAlert` per detection to ``claims/injection_alerts.jsonl``.
In Epic F the alert is logged only (it never changes control flow); the critic acts
on it in Epic G.
"""

from __future__ import annotations

from pathlib import Path

from siftmesh_core.ledgers.jsonl_ledger import append_record, read_records
from siftmesh_core.schemas.injection_alert import InjectionAlert

_INJECTION_ALERTS = Path("claims") / "injection_alerts.jsonl"


def next_alert_id(run_root: Path | str) -> str:
    """Return the next ``ALERT-NNN`` id from the current ledger length."""
    return f"ALERT-{len(read_injection_alerts(run_root)) + 1:03d}"


def append_injection_alert(
    run_root: Path | str,
    alert: InjectionAlert,
    *,
    evidence_root: Path | str | None = None,
) -> Path:
    """Append one injection alert to ``claims/injection_alerts.jsonl``."""
    return append_record(run_root, _INJECTION_ALERTS, alert, evidence_root=evidence_root)


def read_injection_alerts(run_root: Path | str) -> list[InjectionAlert]:
    """Read all injection alerts for a run."""
    return list(read_records(Path(run_root) / _INJECTION_ALERTS, InjectionAlert))
