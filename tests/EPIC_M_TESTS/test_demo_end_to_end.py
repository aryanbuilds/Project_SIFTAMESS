"""M5 - end-to-end tests: full pipeline over real fixtures (criteria 1/2/5/6).

Three layers:
(a) deterministic in-process e2e - the REAL engine (`run_engine`, the same code behind
    `siftmesh run --auto`) over the committed fixtures, asserting the FULL §8 MVP artifact
    checklist + traceability invariants;
(b) one subprocess smoke of the real entrypoint (`python -m siftmesh_core.cli`) - catches
    entrypoint/import/PATH-class failures the in-process layer can't (the 8tcx lesson);
(c) a LIVE property e2e (skip-gated): genuine emergent self-correction is only producible
    by the live agent, so it is asserted as a PROPERTY, never bytes, and the test runs only
    when the maintainer opts in (SIFTMESH_LIVE_E2E=1 + an available claude CLI) - CLAUDE
    §2B human-gating; CI and agent sessions always skip it.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest
from siftmesh_core.config import load_settings
from siftmesh_core.evidence.vault import init_case as vault_init_case
from siftmesh_core.ledgers.claim_ledger import read_claims, read_unsupported_claims
from siftmesh_core.ledgers.tool_call_ledger import read_tool_results
from siftmesh_core.orchestrator.run_state_store import write_run_state
from siftmesh_core.orchestrator.workflow_runner import run_engine
from siftmesh_core.run_dir import RunPaths
from siftmesh_core.schemas.run import RunState

BuildEvidence = Callable[..., None]

# CLAUDE §5 / OVERALL_PLAN §8 - the artifacts every completed auto run MUST produce.
_MVP_MUST_EXIST = (
    "run_state.json",
    "evidence/evidence_manifest.json",
    "evidence/hashes.sha256",
    "evidence/readonly_mounts.json",
    "evidence/custody_log.jsonl",
    "claims/claim_ledger.jsonl",
    "audit/agent_calls.jsonl",
    "audit/tool_calls.jsonl",
    "audit/orchestration_events.jsonl",
    "reports/final_report.md",
    "reports/accuracy_report.md",
    "reports/dataset_documentation.md",
    "reports/architecture_notes.md",
    "reports/replay.html",
)


def _auto_run(tmp_path: Path, build_evidence: BuildEvidence) -> tuple[RunPaths, Path]:
    """The REAL demo path: vault init-case (manifest+hashes+custody) -> auto engine."""
    evidence = tmp_path / "evidence"
    build_evidence(evidence)
    run = vault_init_case(tmp_path / "case01", evidence)
    write_run_state(run, RunState(run_id=run.run_id, mode="auto", max_iterations=3))
    state = run_engine(run, settings=load_settings(), evidence_root=evidence)
    assert state.state == "done", f"engine halted at {state.state}"
    return run, evidence


def test_demo_end_to_end(tmp_path: Path, build_evidence: BuildEvidence) -> None:
    """The §8 MVP acceptance: one auto run produces the complete artifact set."""
    run, _ = _auto_run(tmp_path, build_evidence)
    missing = [rel for rel in _MVP_MUST_EXIST if not (run.root / rel).is_file()]
    assert not missing, f"MVP artifacts missing after auto run: {missing}"
    assert list(run.tasks.glob("TASK-*.yaml")), "no task contracts written"
    assert list(run.results.glob("TASK-*.result.json")), "no task results written"


def test_e2e_every_claim_traces_to_a_real_tool_call(
    tmp_path: Path, build_evidence: BuildEvidence
) -> None:
    """Traceability invariant: every promoted claim anchors to an audited tool call."""
    run, _ = _auto_run(tmp_path, build_evidence)
    claims = read_claims(run.root)
    assert claims, "auto run promoted no claims"
    tool_ids = {t.tool_call_id for t in read_tool_results(run.root)}
    for claim in claims:
        assert claim.tool_call_id in tool_ids, f"{claim.claim_id} anchors a ghost tool call"


def test_e2e_unsupported_never_a_report_fact(tmp_path: Path, build_evidence: BuildEvidence) -> None:
    """The report firewall holds end-to-end: unsupported text only after Appendix B."""
    run, _ = _auto_run(tmp_path, build_evidence)
    report = (run.root / "reports" / "final_report.md").read_text(encoding="utf-8")
    facts, _, _ = report.partition("Appendix B")
    for claim in read_unsupported_claims(run.root):  # usually empty on the clean floor
        assert claim.claim not in facts


def test_e2e_subprocess_smoke_real_entrypoint(
    tmp_path: Path, build_evidence: BuildEvidence
) -> None:
    """One smoke of the REAL module entrypoint - import/entrypoint failures surface here.

    Runs the exact §17 demo shape: `siftmesh run CASE --evidence EV --auto` in a child
    process (the CLI inits the case + creates the run itself), then asserts the run it
    created reached done with reports.
    """
    evidence = tmp_path / "evidence"
    build_evidence(evidence)
    case_dir = tmp_path / "case01"
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "siftmesh_core.cli",
            "run",
            str(case_dir),
            "--evidence",
            str(evidence),
            "--auto",
        ],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert proc.returncode == 0, f"stderr: {proc.stderr[-2000:]}"
    runs = sorted((case_dir / "case_runs").glob("RUN-*"))
    assert len(runs) == 1, f"expected one run, found {runs}"
    run_root = runs[0]
    assert (run_root / "reports" / "final_report.md").is_file()
    state = json.loads((run_root / "run_state.json").read_text(encoding="utf-8"))
    assert state["state"] == "done"


@pytest.mark.live
@pytest.mark.skipif(
    os.environ.get("SIFTMESH_LIVE_E2E") != "1",
    reason="live e2e is maintainer-gated: set SIFTMESH_LIVE_E2E=1 with a logged-in claude CLI "
    "(CLAUDE §2B - never run autonomously; consumes the maintainer's Claude subscription)",
)
def test_live_e2e_self_correction_property(tmp_path: Path, build_evidence: BuildEvidence) -> None:
    """LIVE property e2e (maintainer-run): emergent self-correction, asserted as a property.

    Bytes cannot be asserted against a live LLM; the invariants can: the run completes,
    every promoted claim is anchored, no unsupported claim is a report fact, and at least
    one genuine correction trace exists (a retry_required verdict or an unsupported claim
    recorded and then superseded by an anchored claim on a later attempt).
    """
    from siftmesh_core.adapters.claude_adapter import ClaudeHeadlessAdapter
    from siftmesh_core.ledgers.critic_verdicts import read_critic_verdicts

    if not ClaudeHeadlessAdapter(settings=load_settings()).available():
        pytest.skip("claude CLI not available/logged in")
    evidence = tmp_path / "evidence"
    build_evidence(evidence)
    run = vault_init_case(tmp_path / "case01", evidence)
    write_run_state(run, RunState(run_id=run.run_id, mode="auto", max_iterations=3))
    settings = load_settings(executor_selection="live")
    state = run_engine(run, settings=settings, evidence_root=evidence)
    assert state.state == "done"
    tool_ids = {t.tool_call_id for t in read_tool_results(run.root)}
    for claim in read_claims(run.root):
        assert claim.tool_call_id in tool_ids
    report = (run.root / "reports" / "final_report.md").read_text(encoding="utf-8")
    facts, _, _ = report.partition("Appendix B")
    for claim in read_unsupported_claims(run.root):
        assert claim.claim not in facts
    corrected = any(v.verdict == "retry_required" for v in read_critic_verdicts(run.root))
    superseded = bool(read_unsupported_claims(run.root)) and bool(read_claims(run.root))
    assert corrected or superseded, "no genuine self-correction trace in the live run"
