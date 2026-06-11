"""Pure rendering helpers for the cockpit (Epic O redesign) — content markup, no Textual import.

Kept Textual-free so they unit-test without a terminal. Colors are **theme tokens** (``$success``,
``$primary``, …) that resolve against the active theme — so a theme switch re-colors everything.
Every status is doubled (a glyph AND a word) so it survives no-colour terminals + colour-blindness.
"""

from __future__ import annotations

from siftmesh_core.tui.snapshot import CockpitSnapshot, StageCell

# status → (glyph, colour). Semantic colours (green=good, red=bad) that are UNIVERSAL across themes.
# These render inside BOTH a DataTable cell (Rich markup) and a Static (Textual content markup), so
# they must be concrete Rich colour names — NOT `$theme` tokens (Rich's parser rejects those).
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
    """Markup for a status: coloured glyph + the word (accessibility). Rich-safe colour names."""
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
    gate = f"  gate:[$error]{snap.blocked_gate}[/]" if snap.blocked_gate else ""
    spin = f"{spinner} " if (spinner and not snap.terminal) else ""
    stage = "[bold $success]done[/]" if snap.terminal else f"[bold $accent]{spin}{snap.stage}[/]"
    return (
        f"mode:[$primary]{snap.mode}[/]  stage:{stage}{gate}  "
        f"agent:[$primary]{snap.current_agent}[/]  "
        f"tasks:[bold]{snap.tasks_done}/{snap.tasks_total}[/]  "
        f"iter:{snap.iteration}/{snap.max_iterations}  "
        f"total:[bold]{fmt_duration(snap.total_elapsed_s)}[/]  "
        f"stage:[bold]{fmt_duration(snap.stage_elapsed_s)}[/]"
    )


def _ribbon_cell(cell: StageCell) -> str:
    short = cell.name.replace("create_evidence_vault", "vault").replace("deep_context", "context")
    if cell.state == "done":
        dur = f" {fmt_duration(cell.seconds)}" if cell.seconds else ""
        return f"[$success]✓ {short}{dur}[/]"
    if cell.state == "current":
        return f"[reverse bold $accent] {short} [/]"
    return f"[dim]· {short}[/]"


def ribbon_text(snap: CockpitSnapshot) -> str:
    """The pipeline ribbon (zone 2): the FSM path with done/current/pending."""
    return "  ".join(_ribbon_cell(c) for c in snap.pipeline)


def claims_text(snap: CockpitSnapshot) -> str:
    """Side tab: claim counters + the critic verdict tally."""
    cc = snap.claim_counts
    lines = [
        "[bold]Claims[/]",
        f"  [$success]confirmed {cc['confirmed']}[/]   inferred {cc['inferred']}",
        f"  [$error]contradicted {cc['contradicted']}[/]   [dim]unsupported {cc['unsupported']}[/]",
        "",
        "[bold]Critic verdicts[/]",
    ]
    if snap.verdict_tally:
        lines += [f"  {status_cell(v)}: {n}" for v, n in snap.verdict_tally.items()]
    else:
        lines.append("  [dim](no verdicts yet)[/]")
    if snap.quarantined:
        lines += ["", f"[$secondary]Quarantined: {', '.join(snap.quarantined)}[/]"]
    return "\n".join(lines)


def agents_text(snap: CockpitSnapshot, tiers: dict[str, str] | None = None) -> str:
    """Side tab: the agent-call sessions, each annotated with its honest safety tier."""
    tiers = tiers or {}
    lines = ["[bold]Agent sessions[/]"]
    if snap.agent_sessions:
        for a in snap.agent_sessions[-12:]:
            fb = f" [$warning](←{a.fell_back_from})[/]" if a.fell_back_from else ""
            tier = tiers.get(a.profile)
            badge = f" [dim][{tier}][/]" if tier else ""
            lines.append(f"  {a.task_id}  {status_cell(a.status)}  {a.profile}{badge}{fb}")
    else:
        lines.append("  [dim](none yet)[/]")
    return "\n".join(lines)


def budget_text(snap: CockpitSnapshot) -> str:
    """Side tab: budget-router routing decisions."""
    lines = ["[bold]Budget routing[/]"]
    if snap.budget:
        for row in snap.budget[-12:]:
            base = row.get("base_profile", "?")
            sel = row.get("selected_profile", "?")
            esc = " [$warning]↑escalated[/]" if row.get("escalated") else ""
            lines.append(f"  {base} → {sel}{esc}")
    else:
        lines.append("  [dim](no routing decisions)[/]")
    return "\n".join(lines)
