"""Pure rendering helpers for the cockpit (Epic O) — Rich markup, no Textual import.

Kept Textual-free so they unit-test without a terminal. Every status is doubled (a glyph AND a
word, plus colour) so it survives no-colour terminals and colour-blindness. The cockpit widgets
call these and push the result into a ``Static``/``DataTable``/``RichLog``.
"""

from __future__ import annotations

from siftmesh_core.tui.snapshot import CockpitSnapshot, StageCell

# status → (glyph, colour, canonical word). Collapses the collect/critic/agent vocabularies.
_STATUS_STYLE: dict[str, tuple[str, str]] = {
    "accepted": ("●", "green"),
    "accepted_with_downgrade": ("◍", "green"),
    "success": ("●", "green"),
    "confirmed": ("●", "green"),
    "done": ("●", "green"),
    "dispatched": ("◑", "cyan"),
    "running": ("◑", "cyan"),
    "retry_required": ("◐", "yellow"),
    "retry": ("◐", "yellow"),
    "human_review_required": ("◆", "magenta"),
    "escalation_required": ("◆", "magenta"),
    "fell_back": ("◐", "yellow"),
    "rejected": ("✗", "red"),
    "error": ("✗", "red"),
    "failed": ("✗", "red"),
    "contradicted": ("✗", "red"),
    "pending": ("○", "grey50"),
}


def status_cell(status: str) -> str:
    """Rich markup for a status: coloured glyph + the word (both, for accessibility)."""
    glyph, colour = _STATUS_STYLE.get(status, ("•", "white"))
    return f"[{colour}]{glyph} {status}[/]"


def fmt_duration(seconds: float) -> str:
    """Compact human duration, e.g. 0 → '0s', 75 → '1m15s', 3725 → '1h2m'."""
    s = int(seconds)
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s // 60}m{s % 60:02d}s"
    return f"{s // 3600}h{(s % 3600) // 60:02d}m"


def vitals_text(snap: CockpitSnapshot, *, spinner: str = "") -> str:
    """The single glance line (zone 1)."""
    gate = f"  gate:[red]{snap.blocked_gate}[/]" if snap.blocked_gate else ""
    spin = f"{spinner} " if (spinner and not snap.terminal) else ""
    stage = "[bold green]done[/]" if snap.terminal else f"[bold]{spin}{snap.stage}[/]"
    return (
        f"mode:[cyan]{snap.mode}[/]  stage:{stage}{gate}  "
        f"agent:[cyan]{snap.current_agent}[/]  "
        f"tasks:[bold]{snap.tasks_done}/{snap.tasks_total}[/]  "
        f"iter:{snap.iteration}/{snap.max_iterations}  "
        f"total:[bold]{fmt_duration(snap.total_elapsed_s)}[/]  "
        f"stage:[bold]{fmt_duration(snap.stage_elapsed_s)}[/]"
    )


def _ribbon_cell(cell: StageCell) -> str:
    short = cell.name.replace("create_evidence_vault", "vault").replace("deep_context", "context")
    if cell.state == "done":
        dur = f" {fmt_duration(cell.seconds)}" if cell.seconds else ""
        return f"[green]✓ {short}{dur}[/]"
    if cell.state == "current":
        return f"[reverse bold yellow] {short} [/]"
    return f"[grey50]· {short}[/]"


def ribbon_text(snap: CockpitSnapshot) -> str:
    """The pipeline ribbon (zone 2): the FSM path with done/current/pending."""
    return "  ".join(_ribbon_cell(c) for c in snap.pipeline)


def side_text(snap: CockpitSnapshot) -> str:
    """The peripheral summaries (zone 3 right): claims/critic, agents, budget."""
    cc = snap.claim_counts
    lines = [
        "[bold]Claims[/]",
        f"  [green]confirmed {cc['confirmed']}[/]   inferred {cc['inferred']}",
        f"  [red]contradicted {cc['contradicted']}[/]   [grey50]unsupported {cc['unsupported']}[/]",
        "",
        "[bold]Critic[/]",
    ]
    if snap.verdict_tally:
        lines += [f"  {status_cell(v)}: {n}" for v, n in snap.verdict_tally.items()]
    else:
        lines.append("  [grey50](no verdicts yet)[/]")
    lines += ["", "[bold]Agents[/]"]
    if snap.agent_sessions:
        for a in snap.agent_sessions[-6:]:
            fb = f" [yellow](←{a.fell_back_from})[/]" if a.fell_back_from else ""
            lines.append(f"  {a.task_id} {status_cell(a.status)} {a.profile}{fb}")
    else:
        lines.append("  [grey50](none)[/]")
    if snap.budget:
        lines += ["", "[bold]Budget[/]"]
        for row in snap.budget[-4:]:
            base = row.get("base_profile", "?")
            sel = row.get("selected_profile", "?")
            esc = " [yellow]↑[/]" if row.get("escalated") else ""
            lines.append(f"  {base} → {sel}{esc}")
    if snap.quarantined:
        lines += ["", f"[magenta]Quarantined: {', '.join(snap.quarantined)}[/]"]
    return "\n".join(lines)
