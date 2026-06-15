"""Dataset documentation generator (J5) - provenance + integrity of the ingested evidence.

Pure function of the evidence manifest + the derived-artifacts registry. Degrades to a clear notice
when no manifest exists (run not sealed).
"""

from __future__ import annotations

from pathlib import Path

from siftmesh_core.reports.loader import ReportView, load_report_view
from siftmesh_core.reports.render import MarkdownBuilder, compose_report, write_report
from siftmesh_core.run_dir import RunPaths


def generate_dataset_documentation(
    run: RunPaths, *, evidence_root: Path | str | None = None, view: ReportView | None = None
) -> Path:
    """Write ``reports/dataset_documentation.md``; return its path."""
    v = view or load_report_view(run, evidence_root=evidence_root)
    md = MarkdownBuilder().h1(f"Dataset Documentation - {v.run_id}")
    md.line(
        "Provenance and integrity of every ingested artifact, generated from the sealed manifest."
    )

    if v.manifest is None:
        md.h2("Evidence").line("No evidence manifest present (run not sealed).")
    else:
        m = v.manifest
        md.h2("Case")
        md.bullet(f"Case: {m.case_id}")
        md.bullet(f"Run: {m.run_id}")
        md.bullet(f"Sealed (UTC): {m.created_utc}")
        md.bullet(f"Artifacts: {len(m.files)}")
        md.h2("Artifacts (integrity-verified)")
        md.table(
            ["Path", "sha256", "Size (bytes)", "Type", "Modified (UTC)"],
            [
                [f.path, f.sha256, str(f.size_bytes), f.evidence_type, str(f.mtime_utc)]
                for f in sorted(m.files, key=lambda f: f.path)
            ],
        )

    if v.derived:
        md.h2("Derived artifacts (carved / decompressed)")
        md.line(
            "Originals are never modified; each derived file chains back to its source + producer."
        )
        md.table(
            ["Derived path", "Source artifact", "source_sha256", "Produced by", "Method"],
            [
                [
                    d.derived_path,
                    d.source_artifact,
                    d.source_sha256[:16] + "…",
                    d.tool_call_id,
                    d.extraction_method or "-",
                ]
                for d in v.derived
            ],
        )

    md.h2("License & provenance")
    md.bullet("Evidence provenance and licensing are the responsibility of the case submitter.")
    md.bullet(
        "Integrity anchor: SHA-256 computed at ingest and on each tool access (chain of custody)."
    )
    text = compose_report(
        run_id=v.run_id, run_root=v.run_root, body=md.build(), load_errors=v.load_errors
    )
    return write_report(run, "dataset_documentation.md", text, evidence_root=evidence_root)
