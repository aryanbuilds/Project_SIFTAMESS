"""Cross-run merge (scale fixes / PLAN 11): combine N completed runs into one report.

Lets the operator analyse disk and memory (or portions of a huge case) in SEPARATE runs — deleting
the bulky one with ``prune`` in between — and still get a single combined, evidence-anchored report
with per-run provenance and cross-run contradiction detection. Deterministic core (no LLM); an
opt-in agent SYNTHESIS section is advisory only — it re-presents already-promoted claims and every
claim reference it makes is validated against the merged set (LLM proposes, code decides). The merge
never promotes a new fact; it only collates what each run already promoted.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from siftmesh_core.adapters.judge import invoke_judge_text
from siftmesh_core.config import SiftmeshSettings
from siftmesh_core.ledgers.audit_log import log_event, open_orchestration_log
from siftmesh_core.reports.loader import load_report_view
from siftmesh_core.reports.render import MarkdownBuilder, compose_report, fmt_float, write_report
from siftmesh_core.run_dir import RunPaths, new_run_dir
from siftmesh_core.schemas.claim import Claim

_SHA_SHORT = 16
_MAX_FINDINGS = 50
# Validate on the bare claim-id core, so a fabricated reference is caught regardless of run prefix.
_CLAIM_ID_RE = re.compile(r"\bTASK-\d+-CLAIM-\d+\b")


@dataclass(frozen=True)
class _Source:
    run_id: str
    case_id: str
    objective: str | None
    confirmed: tuple[Claim, ...]
    inferred: tuple[Claim, ...]
    tool_calls: int


def _load_sources(run_dirs: list[Path]) -> list[_Source]:
    sources: list[_Source] = []
    for d in run_dirs:
        view = load_report_view(RunPaths(root=Path(d)))
        sources.append(
            _Source(
                run_id=view.run_id,
                case_id=view.manifest.case_id if view.manifest else "(unknown)",
                objective=view.manifest.incident_objective if view.manifest else None,
                confirmed=view.confirmed,
                inferred=view.inferred,
                tool_calls=len(view.tool_results),
            )
        )
    return sources


def _objective(sources: list[_Source]) -> str | None:
    return next((s.objective for s in sources if s.objective), None)


def _anchor(c: Claim, run_id: str) -> str:
    return (
        f"run `{run_id}` · artifact `{c.source_artifact}` · "
        f"sha256 `{(c.source_sha256 or '')[:_SHA_SHORT]}…` · tool `{c.tool_name}` · "
        f"call `{c.tool_call_id}` · confidence {fmt_float(c.confidence)}"
    )


def _write_merged_claims(run: RunPaths, promoted: list[tuple[str, Claim]]) -> None:
    target = run.claims / "merged_claims.jsonl"
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="\n") as out:
        for rid, c in promoted:
            out.write(json.dumps({"source_run": rid, "claim": c.model_dump(mode="json")}) + "\n")


def _build_body(
    sources: list[_Source],
    promoted: list[tuple[str, Claim]],
    contradictions: list[object],
    objective: str | None,
    synthesis: str | None,
) -> str:
    md = MarkdownBuilder()
    md.h1("SIFTMesh Cross-Run Merged Report")
    md.h2("Executive summary")
    md.bullet(f"Source runs merged: {len(sources)}")
    md.bullet(f"Combined evidence-anchored findings: {len(promoted)}")
    md.bullet(f"Cross-run contradictions detected: {len(contradictions)}")

    md.h2("Source runs")
    md.table(
        ["Run", "Case", "Confirmed", "Inferred", "Tool calls"],
        [
            [s.run_id, s.case_id, str(len(s.confirmed)), str(len(s.inferred)), str(s.tool_calls)]
            for s in sources
        ],
    )

    if objective:
        md.h2("Answer to the incident objective")
        md.line("**Operator objective:**")
        md.bullet(objective[:280])
        bearing = [(rid, c) for rid, c in promoted if c.status in ("confirmed", "inferred")]
        if not bearing:
            md.blank().line("No evidence-anchored finding across the runs bears on this objective.")
        else:
            md.blank().line(
                f"{len(bearing)} finding(s) across {len(sources)} run(s) bear on the objective:"
            )
            for rid, c in bearing[:_MAX_FINDINGS]:
                md.blank().line(f"**{rid}:{c.claim_id}** — {c.claim}")
                md.bullet(_anchor(c, rid))

    md.h2("Combined findings")
    if not promoted:
        md.line("None.")
    else:
        for rid, c in promoted[:_MAX_FINDINGS]:
            md.blank().line(f"**{rid}:{c.claim_id}** ({c.status}) — {c.claim}")
            md.bullet(_anchor(c, rid))
        if len(promoted) > _MAX_FINDINGS:
            md.blank().line(
                f"_… {len(promoted) - _MAX_FINDINGS} more (claims/merged_claims.jsonl)._"
            )

    md.h2("Cross-run contradictions")
    if not contradictions:
        md.line("None detected across the merged runs.")
    else:
        md.line("_Conflicting findings across runs; neither side is reported as settled fact._")
        for rec in contradictions:
            md.bullet(
                f"`{getattr(rec, 'contradiction_id', '?')}` {getattr(rec, 'rule', '?')}: "
                f"{getattr(rec, 'detail', '')}"
            )

    if synthesis:
        md.h2("Cross-run analyst synthesis (agent-proposed; every reference validated)")
        md.line(
            "_Advisory: an LLM synthesis over the merged findings. It promotes NO new fact; every "
            "claim it cites was validated to exist in the merged set above._"
        )
        md.blank().line(synthesis)

    md.h2("Limitations & assumptions")
    md.bullet(
        "This merged report collates findings ALREADY promoted by each source run's deterministic "
        "critic; it introduces no new facts. NOT a claim of court admissibility."
    )
    md.bullet("Timestamps are UTC. Per-run provenance is preserved on every finding.")
    return md.build()


def _synthesize(
    promoted: list[tuple[str, Claim]], objective: str | None, settings: SiftmeshSettings
) -> str | None:
    """Opt-in advisory cross-run synthesis. Returns validated narrative or None (fail-soft)."""
    valid_ids = {c.claim_id for _, c in promoted}  # bare claim-id cores
    if not valid_ids:
        return None
    lines = [f"- {rid}:{c.claim_id} [{c.status}] {c.claim}" for rid, c in promoted[:_MAX_FINDINGS]]
    base = (
        "You are a senior DFIR analyst. Below are evidence-anchored findings from multiple "
        "investigation runs, each tagged RUN:TASK-CLAIM. Write a concise cross-run synthesis "
        "(<= 200 words) of what they collectively indicate"
        + (f", focused on this objective: {objective}. " if objective else ". ")
        + "Cite findings ONLY by their exact RUN:TASK-CLAIM id. Do NOT invent ids or facts.\n\n"
        + "\n".join(lines)
    )
    for _attempt in range(2):
        text = invoke_judge_text(base, settings)
        if not text:
            return None
        cited = set(_CLAIM_ID_RE.findall(text))
        unknown = cited - valid_ids
        if not unknown:
            return text
        base = (
            base + f"\n\nYour previous answer cited unknown ids: {sorted(unknown)}. "
            "Use ONLY ids from the list. Retry."
        )
    return None  # never accept a synthesis that cites a non-existent claim


def merge_runs(
    case_dir: Path | str,
    source_run_dirs: list[Path | str],
    *,
    settings: SiftmeshSettings,
    agent_synthesis: bool = False,
) -> RunPaths:
    """Merge N completed runs into a fresh merge run dir; write the combined report. Returns it."""
    if len(source_run_dirs) < 2:
        raise ValueError("merge needs at least two source runs (--run RUN_A --run RUN_B)")
    sources = _load_sources([Path(d) for d in source_run_dirs])
    promoted: list[tuple[str, Claim]] = []
    for s in sources:
        for c in (*s.confirmed, *s.inferred):
            promoted.append((s.run_id, c))

    merge_run = new_run_dir(base=Path(case_dir) / "case_runs")
    audit = open_orchestration_log(merge_run.orchestration_events, merge_run.run_id)
    log_event(audit, "merge_started", sources=[s.run_id for s in sources])

    _write_merged_claims(merge_run, promoted)
    (merge_run.context / "merge_sources.json").write_text(
        json.dumps(
            {"sources": [{"run_id": s.run_id, "case_id": s.case_id} for s in sources]}, indent=2
        )
        + "\n",
        encoding="utf-8",
    )

    from siftmesh_core.orchestrator.critic import detect_contradictions

    contra_map = detect_contradictions([c for _, c in promoted])
    contradictions = sorted(
        {rec.contradiction_id: rec for rec in contra_map.values()}.values(),
        key=lambda r: r.contradiction_id,
    )

    objective = _objective(sources)
    synthesis = _synthesize(promoted, objective, settings) if agent_synthesis and promoted else None
    body = _build_body(sources, promoted, list(contradictions), objective, synthesis)
    write_report(
        merge_run,
        "final_report.md",
        compose_report(run_id=merge_run.run_id, run_root=merge_run.root, body=body),
    )
    log_event(
        audit,
        "merge_complete",
        sources=len(sources),
        findings=len(promoted),
        contradictions=len(contradictions),
        synthesis=bool(synthesis),
    )
    return merge_run
