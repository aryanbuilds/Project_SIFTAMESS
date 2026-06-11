"""Re-critique must be idempotent (bug Project_SIFTAMESS-myl7).

Running `critique` more than once (e.g. during judge debugging) must NOT duplicate promoted claims —
even when the two id schemes collide (floor ``TASK-CLAIM-NNN`` vs live ``TASK-A{n}-CLAIM-NNN``).
The fix dedups on a content key (task + source_sha256 + tool_call_id + normalized text), not the id.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from siftmesh_core.config import load_settings
from siftmesh_core.ledgers.claim_ledger import read_claims
from siftmesh_core.orchestrator.critic import _claim_key, critique_run
from siftmesh_core.run_dir import RunPaths

MakeRealRun = Callable[..., tuple[RunPaths, Path]]


def test_double_critique_promotes_no_duplicate_claims(make_real_run: MakeRealRun) -> None:
    run, evidence = make_real_run(dispatch=True, critique=True)
    once = read_claims(run.root)
    assert once, "the floor run must promote real claims to critique"

    # Re-critique twice more (idempotency under repeated passes — the myl7 scenario).
    critique_run(run, settings=load_settings(), evidence_root=evidence)
    critique_run(run, settings=load_settings(), evidence_root=evidence)
    after = read_claims(run.root)

    # No new rows, and no duplicate CONTENT keys (the real defect: same finding, two id schemes).
    assert len(after) == len(once)
    keys = [_claim_key(c) for c in after]
    assert len(keys) == len(set(keys)), "duplicate claim content across re-critique passes"


def test_content_key_collapses_dual_id_scheme() -> None:
    from siftmesh_core.schemas.claim import Claim

    base = {
        "task_id": "TASK-002",
        "status": "confirmed",
        "claim": "PowerShell  4104 script block   observed",  # whitespace differs below
        "confidence": 0.9,
        "evidence_type": "powershell_log",
        "source_artifact": "PowerShell-Operational.evtx",
        "source_sha256": "a" * 64,
        "tool_name": "parse_evtx_powershell",
        "tool_call_id": "TOOL-002",
        "supporting_evidence_refs": ["TOOL-002"],
    }
    floor = Claim(claim_id="TASK-002-CLAIM-001", **base)
    live = Claim(
        claim_id="TASK-002-A1-CLAIM-001",
        **{
            **base,
            "claim": "powershell 4104 script block observed",
        },  # same finding, diff casing/ws
    )
    assert _claim_key(floor) == _claim_key(live)  # the dual id scheme collapses to one content key
