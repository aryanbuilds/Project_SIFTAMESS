"""B5 keystone (bd vd2t): deterministic parallel dispatch == sequential, byte-for-byte.

Parallel dispatch executes tasks concurrently into per-task staging dirs, then commits in contract
order with renumbered ids. The committed ledgers must be IDENTICAL to a sequential run in every
order-dependent way (ids, references, order, file names + content) - only wall-clock timestamps may
differ. Proven over the deterministic floor (no keys), repeated to flush ordering races.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from pathlib import Path

from siftmesh_core.config import load_settings
from siftmesh_core.ledgers.agent_calls import read_agent_calls
from siftmesh_core.ledgers.claim_ledger import read_claims, read_unsupported_claims
from siftmesh_core.ledgers.injection_alerts import read_injection_alerts
from siftmesh_core.ledgers.tool_call_ledger import read_tool_results
from siftmesh_core.orchestrator.scheduler import dispatch_run
from siftmesh_core.run_dir import RunPaths

MakeRealRun = Callable[..., tuple[RunPaths, Path]]


def _project(run: RunPaths) -> dict[str, object]:
    """Order-dependent fingerprint of a dispatched run (everything EXCEPT wall-clock timestamps)."""
    tools = [
        (
            t.tool_call_id,
            t.tool_name,
            t.source_artifact,
            t.source_sha256,
            t.status,
            t.backend,
            t.structured_result_path,
            t.raw_output_path,
        )
        for t in read_tool_results(run.root)
    ]
    claims = [
        (
            c.claim_id,
            c.status,
            c.tool_call_id,
            tuple(c.supporting_evidence_refs),
            c.source_sha256,
            c.claim,
        )
        for c in (*read_claims(run.root), *read_unsupported_claims(run.root))
    ]
    agents = [
        (a.agent_call_id, a.task_id, a.profile, a.adapter, a.status, a.attempt, a.fell_back_from)
        for a in read_agent_calls(run.root)
    ]
    alerts = [
        (a.alert_id, a.signature, a.task_id, a.source_artifact)
        for a in read_injection_alerts(run.root)
    ]
    derived = json.loads((run.root / "evidence" / "derived_artifacts.json").read_text())["derived"]
    derived_proj = [
        (d["derived_path"], d["tool_call_id"], d["source_artifact"], d.get("derived_sha256"))
        for d in derived
    ]
    # Structured result file CONTENTS (the parser output is deterministic for the same evidence).
    structured = {
        p.name: p.read_text(encoding="utf-8")
        for p in sorted(run.root.glob("results/TOOL-*.structured.json"))
    }
    # Result envelopes: each task's claim ids + their tool-call refs.
    envelopes = {}
    for rp in sorted(run.root.glob("results/TASK-*.result.json")):
        env = json.loads(rp.read_text(encoding="utf-8"))
        envelopes[rp.name] = [
            (c["claim_id"], c.get("tool_call_id"), tuple(c.get("supporting_evidence_refs", [])))
            for c in env.get("claims", [])
        ]
    return {
        "tools": tools,
        "claims": claims,
        "agents": agents,
        "alerts": alerts,
        "derived": derived_proj,
        "structured": structured,
        "envelopes": envelopes,
    }


def _dispatch_copy(planned: RunPaths, evidence: Path, dst: Path, *, parallel: bool) -> RunPaths:
    """Copy the planned run to `dst` (same basename → same run_id) and dispatch it."""
    shutil.copytree(planned.root, dst)
    run = RunPaths(root=dst)
    settings = load_settings().model_copy(update={"parallel_dispatch": parallel})
    dispatch_run(run, settings=settings, evidence_override=evidence)
    return run


def test_parallel_dispatch_is_byte_identical_to_sequential(
    make_real_run: MakeRealRun, tmp_path: Path
) -> None:
    planned, evidence = make_real_run(plan=True)  # multi-task planned run, not yet dispatched
    n_tasks = len(list(planned.tasks.glob("TASK-*.yaml")))
    assert n_tasks > 1, "need >1 task for parallelism to engage"

    seq = _project(
        _dispatch_copy(planned, evidence, tmp_path / "seq" / planned.run_id, parallel=False)
    )

    # Repeat the parallel run several times to flush out ordering races (it must match every time).
    for i in range(5):
        par = _project(
            _dispatch_copy(planned, evidence, tmp_path / f"par{i}" / planned.run_id, parallel=True)
        )
        assert par == seq, f"parallel run {i} diverged from sequential"


def test_parallel_path_leaves_no_staging_dir(make_real_run: MakeRealRun, tmp_path: Path) -> None:
    planned, evidence = make_real_run(plan=True)
    run = _dispatch_copy(planned, evidence, tmp_path / "p" / planned.run_id, parallel=True)
    assert not (run.root / ".staging").exists()  # cleaned up after commit


def test_default_is_sequential(make_real_run: MakeRealRun) -> None:
    # parallel_dispatch defaults OFF -> a plain dispatch never creates a staging dir.
    run, _ = make_real_run(dispatch=True)
    assert not (run.root / ".staging").exists()
