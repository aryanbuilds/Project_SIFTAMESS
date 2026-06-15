"""Replay (J7) - text replay (MVP) + self-contained HTML, both deterministic.

The replayable audit trail: every orchestration event in chronological order ``(timestamp, line)``
from ``audit/orchestration_events.jsonl``. The text replay reconstructs the timeline from the JSONL
alone (terminal output); ``replay.html`` is a self-contained static page (inline CSS, NO external
assets). Both are pure functions of the ledger; the HTML body is golden-byte-stable (generation
metadata lives in the excluded header).
"""

from __future__ import annotations

from pathlib import Path

from siftmesh_core.reports.loader import OrchestrationEvent, ReportView, load_report_view
from siftmesh_core.reports.render import compose_report, render_body_only, write_report
from siftmesh_core.run_dir import RunPaths

_KINDS = ("retry", "verdict", "decision", "tool", "dispatch", "gate", "report", "injection")
_DETAIL_LIMIT = 200


def _kind(event: str) -> str:
    for key in _KINDS:
        if key in event:
            return key
    return "info"


def _detail(e: OrchestrationEvent) -> str:
    if not e.extra:
        return ""
    return "; ".join(f"{k}={v}" for k, v in sorted(e.extra.items()))[:_DETAIL_LIMIT]


def render_text_replay(view: ReportView) -> str:
    """Deterministic text timeline (for ``siftmesh replay`` stdout)."""
    lines = [f"SIFTMesh replay - {view.run_id}", f"{len(view.events)} orchestration events", ""]
    for i, e in enumerate(view.events, 1):
        detail = _detail(e)
        lines.append(f"{i:04d}  {e.timestamp}  {e.event}" + (f"  [{detail}]" if detail else ""))
    if not view.events:
        lines.append("(no orchestration events recorded)")
    return "\n".join(lines) + "\n"


def generate_replay_html(
    run: RunPaths, *, evidence_root: Path | str | None = None, view: ReportView | None = None
) -> Path:
    """Write a self-contained ``reports/replay.html``; return its path."""
    v = view or load_report_view(run, evidence_root=evidence_root)
    rows = [
        {"timestamp": e.timestamp, "event": e.event, "detail": _detail(e), "kind": _kind(e.event)}
        for e in v.events
    ]
    body = render_body_only(
        "replay.html.j2", {"run_id": v.run_id, "events": rows, "event_count": len(rows)}
    )
    text = compose_report(
        run_id=v.run_id, run_root=v.run_root, body=body, load_errors=v.load_errors
    )
    return write_report(run, "replay.html", text, evidence_root=evidence_root)
