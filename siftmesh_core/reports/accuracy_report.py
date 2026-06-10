"""Accuracy / false-positive report generator (J4) — dual mode.

A blind investigation has no ground truth, so the DEFAULT is an honest **self-assessment**:
confidence bands, corroboration counts, unsupported disclosure, critic-caught FPs, and coverage
gaps — never a fabricated precision/recall number. When a ground-truth ``expected_findings.md`` is
provided (``--expected`` or ``examples/demo_case/expected_findings.md``), a heuristic **diff mode**
adds precision / recall / FP-rate and shows the planted FP as caught-by-critic.
"""

from __future__ import annotations

from pathlib import Path

from siftmesh_core.reports.loader import ReportView, load_report_view
from siftmesh_core.reports.render import (
    MarkdownBuilder,
    compose_report,
    fmt_pct,
    write_report,
)
from siftmesh_core.run_dir import RunPaths
from siftmesh_core.schemas.claim import Claim

_BANDS = (
    ("0.90-1.00", 0.90, 1.01),
    ("0.70-0.89", 0.70, 0.90),
    ("0.50-0.69", 0.50, 0.70),
    ("0.00-0.49", 0.0, 0.50),
)


def generate_accuracy_report(
    run: RunPaths,
    *,
    evidence_root: Path | str | None = None,
    view: ReportView | None = None,
    expected_findings: Path | str | None = None,
) -> Path:
    """Write ``reports/accuracy_report.md``; return its path."""
    v = view or load_report_view(run, evidence_root=evidence_root)
    md = MarkdownBuilder().h1(f"Accuracy & False-Positive Report — {v.run_id}")

    expected = Path(expected_findings) if expected_findings else None
    if expected is not None and expected.is_file():
        md.line(f"_Ground-truth diff against `{expected.name}` (heuristic substring match)._")
        _diff_mode(md, v, expected)
    else:
        md.line(
            "_No ground-truth baseline — honest self-assessment (no fabricated precision/recall)._"
        )
        _self_assessment(md, v)

    text = compose_report(
        run_id=v.run_id, run_root=v.run_root, body=md.build(), load_errors=v.load_errors
    )
    return write_report(run, "accuracy_report.md", text, evidence_root=evidence_root)


def _self_assessment(md: MarkdownBuilder, v: ReportView) -> None:
    findings = (*v.confirmed, *v.inferred)
    md.h2("Results summary")
    md.bullet(f"Confirmed findings: {len(v.confirmed)}")
    md.bullet(f"Inferred findings: {len(v.inferred)}")
    md.bullet(f"Unsupported (rejected, not facts): {len(v.unsupported)}")
    md.bullet(f"Contradictions detected: {len(v.contradictions)}")
    md.bullet(f"Confidence downgrades by critic: {len(v.confidence_changes)}")

    md.h2("Confidence distribution (final, post-downgrade)")
    rows = []
    for label, lo, hi in _BANDS:
        n = sum(1 for c in findings if lo <= _final_conf(v, c) < hi)
        rows.append([label, str(n)])
    md.table(["Confidence band", "Findings"], rows)

    md.h2("Corroboration")
    groups: dict[tuple[str, str], int] = {}
    for c in findings:
        groups[(c.evidence_type, c.source_artifact or "")] = (
            groups.get((c.evidence_type, c.source_artifact or ""), 0) + 1
        )
    corroborated = sum(1 for n in groups.values() if n >= 2)
    single = sum(1 for n in groups.values() if n == 1)
    md.bullet(f"Multi-claim (corroborated ≥2 on same artifact+type) groups: {corroborated}")
    md.bullet(f"Single-source finding groups: {single} (lower confidence by construction)")

    md.h2("False-positive control")
    md.bullet(
        f"Claims rejected by the critic for missing evidence: {len(v.unsupported)} "
        "(never reported as fact — Appendix B of the final report)."
    )
    md.bullet(f"Over-broad claims downgraded: {len(v.confidence_changes)}.")
    md.bullet(f"Contradictions escalated rather than asserted: {len(v.contradictions)}.")

    md.h2("Coverage gaps")
    cov = [f for f in v.followups if f.reason in ("coverage_gap", "derived_gap")]
    md.bullet(f"Coverage/derived follow-ups raised: {len(cov)}.")
    if v.claims_on_failed_tools:
        md.bullet(f"Findings on a partly-failed tool: {len(v.claims_on_failed_tools)} (verify).")
    if v.manifest is not None:
        examined = {c.source_artifact for c in findings if c.source_artifact}
        uncovered = [f.path for f in v.manifest.files if f.path not in examined]
        md.bullet(f"Manifest artifacts with no finding: {len(uncovered)}.")


def _diff_mode(md: MarkdownBuilder, v: ReportView, expected_path: Path) -> None:
    expected = _parse_expected(expected_path)
    confirmed_text = [c.claim for c in (*v.confirmed, *v.inferred)]
    tp = [
        e
        for e in expected
        if any(_norm(e) in _norm(t) or _norm(t) in _norm(e) for t in confirmed_text)
    ]
    fn = [e for e in expected if e not in tp]
    # FP = confirmed findings matching no expected item:
    fp = [
        t
        for t in confirmed_text
        if not any(_norm(e) in _norm(t) or _norm(t) in _norm(e) for e in expected)
    ]
    n_tp, n_fp, n_fn = len(tp), len(fp), len(fn)
    precision = n_tp / (n_tp + n_fp) if (n_tp + n_fp) else None
    recall = n_tp / (n_tp + n_fn) if (n_tp + n_fn) else None
    md.h2("Results vs ground truth")
    md.table(
        ["Metric", "Value"],
        [
            ["Expected findings", str(len(expected))],
            ["True positives", str(n_tp)],
            ["False positives", str(n_fp)],
            ["False negatives", str(n_fn)],
            ["Precision", fmt_pct(precision) if precision is not None else "n/a"],
            ["Recall", fmt_pct(recall) if recall is not None else "n/a"],
        ],
    )
    md.line(f"_Confidence note: heuristic substring match over {len(confirmed_text)} findings._")
    if v.unsupported:
        md.h2("Critic-caught false positives")
        md.line(
            f"{len(v.unsupported)} agent claim(s) were rejected before reaching the findings "
            "(caught-by-critic, not counted as FP above)."
        )
    if fn:
        md.h2("False negatives (not found)")
        for e in fn[:50]:
            md.bullet(_truncate(e, 100))


# ── helpers ────────────────────────────────────────────────────────────────────


def _final_conf(v: ReportView, c: Claim) -> float:
    if c.claim_id in v.confidence_by_claim_id:
        return v.confidence_by_claim_id[c.claim_id][1]
    return c.confidence


def _parse_expected(path: Path) -> list[str]:
    """Extract expected-finding lines from a markdown file (bullets / non-heading lines)."""
    out: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith(("- ", "* ", "+ ")):
            line = line[2:].strip()
        if line:
            out.append(line)
    return out


def _norm(text: str) -> str:
    return " ".join(text.lower().split())


def _truncate(text: str, limit: int) -> str:
    text = text.replace("\n", " ").replace("|", "\\|").strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"
