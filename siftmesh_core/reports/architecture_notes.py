"""Run-specific architecture notes generator (J6).

What this *run* did: mode, state, gate decisions, guardrails active (with run-specific evidence),
security boundaries crossed. Complements the static docs/architecture.md. Degrades when the engine
snapshot (run_state.json) is absent by reconstructing from orchestration events.
"""

from __future__ import annotations

from pathlib import Path

from siftmesh_core.reports.loader import ReportView, load_report_view
from siftmesh_core.reports.render import MarkdownBuilder, compose_report, write_report
from siftmesh_core.run_dir import RunPaths


def generate_architecture_notes(
    run: RunPaths, *, evidence_root: Path | str | None = None, view: ReportView | None = None
) -> Path:
    """Write ``reports/architecture_notes.md``; return its path."""
    v = view or load_report_view(run, evidence_root=evidence_root)
    md = MarkdownBuilder().h1(f"Run Architecture Notes — {v.run_id}")

    md.h2("Run mode & state")
    if v.run_state is not None:
        rs = v.run_state
        md.bullet(f"Mode: {rs.mode}")
        md.bullet(f"State: {rs.state}{' (terminal)' if rs.terminal else ''}")
        md.bullet(f"Self-correction iterations: {rs.iteration}/{rs.max_iterations}")
        if rs.gates:
            md.bullet("Gates: " + ", ".join(f"{g}={s}" for g, s in sorted(rs.gates.items())))
        if rs.blocked_gate:
            md.bullet(f"Halted awaiting approval at: {rs.blocked_gate}")
    else:
        md.line("No engine snapshot (run driven by discrete CLI commands); see events below.")

    md.h2("Guardrails active (this run)")
    inj = len(v.injection_alerts)
    consequences = sum(1 for e in v.events if e.event == "injection_consequence_applied")
    fell_back = sum(1 for a in v.agent_calls if a.status == "fell_back")
    md.bullet("Path policy: all writes confined to the run directory (originals never modified).")
    md.bullet("Typed-tool allowlist: only the 10 audited tools; no raw shell / destructive tools.")
    md.bullet("Evidence read-only: hashed at ingest; re-hashed on each tool access (custody).")
    md.bullet(f"Spotlighting: {inj} injection alert(s); {consequences} consequence(s) applied.")
    md.bullet(f"Adapter fall-back to deterministic floor: {fell_back} time(s).")

    md.h2("Security boundaries crossed")
    extractions = [c for c in (*v.confirmed, *v.inferred) if c.evidence_type == "image_extraction"]
    memory = [c for c in (*v.confirmed, *v.inferred) if c.evidence_type == "memory_analysis"]
    if v.derived:
        md.bullet(
            f"Derived-artifact extraction/decompression: {len(v.derived)} artifact(s) carved."
        )
    if extractions:
        md.bullet(f"Disk-image extraction (Sleuthkit): {len(extractions)} claim(s).")
    if memory:
        md.bullet(f"Memory analysis (Volatility 3, subprocess-only): {len(memory)} claim(s).")
    if not (v.derived or extractions or memory):
        md.bullet("None beyond read-only artifact parsing.")

    gate_events = [e for e in v.events if "gate" in e.event]
    if gate_events:
        md.h2("Gate decisions (from the audit trail)")
        for e in gate_events:
            md.bullet(f"{e.timestamp} — {e.event} {('· ' + str(e.extra)) if e.extra else ''}")

    text = compose_report(
        run_id=v.run_id, run_root=v.run_root, body=md.build(), load_errors=v.load_errors
    )
    return write_report(run, "architecture_notes.md", text, evidence_root=evidence_root)
