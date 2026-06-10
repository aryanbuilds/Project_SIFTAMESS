"""Real-evidence-run hardening: non-actionable evidence is surfaced (not silently dropped),
and the dispatch cap error tells the operator how to raise it (bd 0jv usability).

Driven by the real ROCBA shape: a disk image + a zipped memory capture + a context pptx.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest
from siftmesh_core.config import load_settings
from siftmesh_core.orchestrator.planner import generate_plan
from siftmesh_core.orchestrator.scheduler import CapError, dispatch_run
from siftmesh_core.run_dir import RunPaths

SyntheticRun = Callable[..., RunPaths]

# The real ROCBA evidence shape (names mirror ~/projects/data).
_ROCBA = ("rocba-cdrive.e01", "Rocba-Memory.zip", "ROCBA-BACKGROUND.pptx")


def test_non_actionable_evidence_surfaced_in_assumptions(synthetic_run: SyntheticRun) -> None:
    run = synthetic_run(_ROCBA)
    generate_plan(run, settings=load_settings())
    assumptions = (run.root / "context" / "assumptions.md").read_text(encoding="utf-8")
    # the zip + pptx must be named (never silently dropped); the .e01 is actionable (extract)
    assert "Rocba-Memory.zip" in assumptions
    assert "ROCBA-BACKGROUND.pptx" in assumptions
    assert "decompress" in assumptions  # the archive gets a concrete how-to
    assert "rocba-cdrive.e01" not in assumptions  # actionable -> a real task, not the skip list


def test_non_actionable_evidence_logged_to_audit(synthetic_run: SyntheticRun) -> None:
    run = synthetic_run(_ROCBA)
    generate_plan(run, settings=load_settings())
    events = [
        json.loads(line)
        for line in run.orchestration_events.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    skipped = [e for e in events if e.get("event") == "plan_non_actionable_evidence"]
    assert len(skipped) == 1
    assert skipped[0]["count"] == 2
    assert "Rocba-Memory.zip" in skipped[0]["artifacts"]


def test_all_actionable_evidence_has_no_skip_section(synthetic_run: SyntheticRun) -> None:
    # The committed-fixture shape (all actionable) must NOT grow a skip section.
    run = synthetic_run(("Security.evtx", "CMD.EXE-1.pf"))
    generate_plan(run, settings=load_settings())
    assumptions = (run.root / "context" / "assumptions.md").read_text(encoding="utf-8")
    assert "not directly planned" not in assumptions


def test_dispatch_cap_error_is_actionable(synthetic_run: SyntheticRun, tmp_path: Path) -> None:
    # Per-family aggregation (bd 1xy6) collapses the 12 prefetch files into ONE task (+timeline)
    # = 2; a max_agent_tasks=1 cap still trips the actionable error. (Aggregation is also what
    # makes the default cap of 10 comfortably enough for a real disk image now.)
    run = synthetic_run(tuple(f"CMD{i}.EXE-{i:08d}.pf" for i in range(12)))
    base = load_settings()
    settings = base.model_copy(update={"caps": base.caps.model_copy(update={"max_agent_tasks": 1})})
    generate_plan(run, settings=settings)
    evidence = tmp_path / "evidence"  # a real dir outside the run; unused before the cap raises
    evidence.mkdir(exist_ok=True)
    with pytest.raises(CapError, match="--max-agent-tasks"):
        dispatch_run(run, settings=settings, evidence_override=str(evidence))


def test_max_agent_tasks_override_raises_ceiling() -> None:
    base = load_settings()
    assert base.caps.max_agent_tasks == 10
    raised = base.model_copy(update={"caps": base.caps.model_copy(update={"max_agent_tasks": 300})})
    assert raised.caps.max_agent_tasks == 300
    assert raised.caps.max_iterations == base.caps.max_iterations  # other caps untouched
