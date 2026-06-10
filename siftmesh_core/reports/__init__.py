"""Reports & Replay (Epic J) — deterministic, code-generated artifacts from the run-dir ledgers.

Public surface: ``generate_all_reports`` loads the :class:`ReportView` ONCE and writes every report
+ ``replay.html`` (one identical snapshot). Reports are byte-deterministic functions of the ledgers
(NO LLM at report time) — the replayable-audit differentiator.
"""

from __future__ import annotations

from pathlib import Path

from siftmesh_core.reports.accuracy_report import generate_accuracy_report
from siftmesh_core.reports.architecture_notes import generate_architecture_notes
from siftmesh_core.reports.dataset_documentation import generate_dataset_documentation
from siftmesh_core.reports.final_report import generate_final_report
from siftmesh_core.reports.loader import ReportLoadError, ReportView, load_report_view
from siftmesh_core.reports.render import split_body
from siftmesh_core.reports.replay import generate_replay_html, render_text_replay
from siftmesh_core.run_dir import RunPaths

__all__ = [
    "ReportLoadError",
    "ReportView",
    "generate_accuracy_report",
    "generate_all_reports",
    "generate_architecture_notes",
    "generate_dataset_documentation",
    "generate_final_report",
    "generate_replay_html",
    "load_report_view",
    "render_text_replay",
    "split_body",
]


def generate_all_reports(
    run: RunPaths,
    *,
    evidence_root: Path | str | None = None,
    strict: bool = True,
    expected_findings: Path | str | None = None,
) -> list[Path]:
    """Load the view once and write all five reports + replay.html; return the written paths."""
    view = load_report_view(run, evidence_root=evidence_root, strict=strict)
    return [
        generate_final_report(run, evidence_root=evidence_root, view=view),
        generate_accuracy_report(
            run, evidence_root=evidence_root, view=view, expected_findings=expected_findings
        ),
        generate_dataset_documentation(run, evidence_root=evidence_root, view=view),
        generate_architecture_notes(run, evidence_root=evidence_root, view=view),
        generate_replay_html(run, evidence_root=evidence_root, view=view),
    ]
