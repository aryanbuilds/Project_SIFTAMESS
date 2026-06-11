"""Full-auto refinement: auto-decompress pre-existing archives + quarantine (never halt) one
flagged task. Public fixtures only; no live agent, no SANS evidence (CLAUDE §2B).
"""

from __future__ import annotations

import zipfile
from collections.abc import Callable
from pathlib import Path

import pytest
from siftmesh_core.config import load_settings
from siftmesh_core.evidence.derived import read_derived
from siftmesh_core.evidence.vault import init_case
from siftmesh_core.ledgers.audit_log import open_orchestration_log
from siftmesh_core.orchestrator import workflow_runner
from siftmesh_core.orchestrator.run_state_store import write_run_state
from siftmesh_core.orchestrator.ultraworker import RunDecision
from siftmesh_core.orchestrator.workflow_runner import run_engine
from siftmesh_core.run_dir import RunPaths
from siftmesh_core.schemas.run import RunState
from siftmesh_core.schemas.task import TaskContract
from siftmesh_core.schemas.yaml_io import read_yaml_model

# A fake raw memory image: crashdump64 magic + padding so it is the archive's largest member.
_FAKE_IMAGE = b"PAGEDU64" + b"\x00" * 8192

BuiltRun = Callable[..., tuple[RunPaths, Path]]


def _case_with_zip(tmp_path: Path, build_evidence: Callable[..., None]) -> tuple[RunPaths, Path]:
    """Evidence = the real forensic fixtures PLUS a plain memory zip; init-case over it."""
    evidence = tmp_path / "evidence"
    build_evidence(evidence)
    with zipfile.ZipFile(evidence / "Rocba-Memory.zip", "w") as zf:
        zf.writestr("Rocba-Memory.raw", _FAKE_IMAGE)
    run = init_case(tmp_path / "case", evidence)
    return run, evidence


# ── archive auto-decompress ──────────────────────────────────────────────────────


def test_auto_handle_archives_is_idempotent(
    tmp_path: Path, build_evidence: Callable[..., None]
) -> None:
    run, evidence = _case_with_zip(tmp_path, build_evidence)
    audit = open_orchestration_log(run.orchestration_events, run.run_id)

    workflow_runner._auto_handle_archives(run, evidence_root=evidence, audit=audit)
    workflow_runner._auto_handle_archives(run, evidence_root=evidence, audit=audit)  # re-entry

    derived = read_derived(run.root)
    decomps = [d for d in derived if d.source_artifact == "Rocba-Memory.zip"]
    assert len(decomps) == 1  # decompressed exactly once (resume-safe)
    assert (run.evidence / "extracted" / "Rocba-Memory.raw").read_bytes() == _FAKE_IMAGE


def test_full_auto_decompresses_and_ingests_archive(
    tmp_path: Path, build_evidence: Callable[..., None]
) -> None:
    run, evidence = _case_with_zip(tmp_path, build_evidence)
    write_run_state(run, RunState(run_id=run.run_id, mode="auto", max_iterations=3))

    state = run_engine(run, settings=load_settings(), evidence_root=evidence)

    # The memory zip was auto-decompressed (no manual `decompress` + `ingest-derived`).
    assert (run.evidence / "extracted" / "Rocba-Memory.raw").is_file()
    assert any(d.source_artifact == "Rocba-Memory.zip" for d in read_derived(run.root))
    events = run.orchestration_events.read_text(encoding="utf-8")
    assert "archive_auto_decompress" in events and "decompress_done" in events
    # …and the derived image was auto-ingested into a real memory-analysis task.
    memory_tasks = [
        read_yaml_model(TaskContract, p)
        for p in run.tasks.glob("TASK-*.yaml")
        if read_yaml_model(TaskContract, p).allowed_tools == ["analyze_memory"]
    ]
    assert memory_tasks, "the decompressed image was not ingested as a memory task"
    assert isinstance(state, RunState)  # engine completed the loop without crashing


def test_manual_mode_does_not_auto_decompress(
    tmp_path: Path, build_evidence: Callable[..., None]
) -> None:
    run, evidence = _case_with_zip(tmp_path, build_evidence)
    write_run_state(run, RunState(run_id=run.run_id, mode="manual", max_iterations=3))
    # manual = single transition (init -> create_evidence_vault); no auto-decompress for manual ops.
    run_engine(run, settings=load_settings(), evidence_root=evidence, single_step=True)
    assert not (run.evidence / "extracted").exists()


# ── quarantine: --auto proceeds, guided halts ────────────────────────────────────


def _human_review_then_done() -> Callable[..., RunDecision]:
    """A fake aggregator: TASK-001 flips human_review until excluded, then the rest is done."""

    def _fake(
        run: RunPaths,
        state: RunState,
        *,
        settings: object,
        exclude: frozenset[str] = frozenset(),
        verdicts: object = None,
    ) -> RunDecision:
        if "TASK-001" in exclude:
            return RunDecision("done", "rest accepted", ())
        return RunDecision("human_review", "forced injection flag", ("TASK-001",))

    return _fake


def test_auto_quarantines_flagged_task_and_reaches_done(
    built_run: BuiltRun, monkeypatch: pytest.MonkeyPatch
) -> None:
    run, evidence = built_run(mode="auto", max_iterations=3)
    monkeypatch.setattr(workflow_runner, "aggregate_decision", _human_review_then_done())

    state = run_engine(run, settings=load_settings(), evidence_root=evidence)

    assert state.terminal and state.state == "done"  # full-auto ran to completion
    assert "TASK-001" in state.quarantined_tasks
    assert "task_quarantined" in run.orchestration_events.read_text(encoding="utf-8")


def test_decide_guided_mode_halts_without_quarantine(
    make_real_run: Callable[..., tuple[RunPaths, Path]], monkeypatch: pytest.MonkeyPatch
) -> None:
    run, evidence = make_real_run(plan=True)
    audit = open_orchestration_log(run.orchestration_events, run.run_id)

    def _always_human(
        run: RunPaths,
        state: RunState,
        *,
        settings: object,
        exclude: frozenset[str] = frozenset(),
        verdicts: object = None,
    ) -> RunDecision:
        return RunDecision("human_review", "forced", ("TASK-001",))

    monkeypatch.setattr(workflow_runner, "aggregate_decision", _always_human)
    state = RunState(run_id=run.run_id, mode="auto_human_loop", state="decide")
    new_state, target = workflow_runner._decide(
        run, state, settings=load_settings(), evidence_root=evidence, audit=audit
    )
    assert target == "decide"  # halt (target == current)
    assert new_state.blocked_gate == "retry"
    assert new_state.quarantined_tasks == []  # guided mode never quarantines
