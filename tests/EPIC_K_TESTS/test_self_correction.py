"""Epic K, K3 - live self-correction loop (claim capture + critic-feedback retry).

The live agent subprocess is ALWAYS mocked (CI-safe, no keys, §2B); the GOVERNANCE is real - a real
typed tool call seeds a real ``tool_call_id`` + manifest hash, and the real deterministic critic
grades the agent's claims. The headline test proves the emergent loop end-to-end: the mocked agent
over-claims without an anchor on the first attempt, the critic rejects it, the rejection feedback
flows back into the retry prompt, and the agent's corrected (properly anchored) claim is accepted.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest
from siftmesh_core.adapters.agent_result import parse_agent_result
from siftmesh_core.adapters.base import AdapterContext
from siftmesh_core.adapters.claude_adapter import ClaudeHeadlessAdapter
from siftmesh_core.config import load_settings
from siftmesh_core.evidence.manifest import build_manifest_from_dir, write_manifest
from siftmesh_core.evidence.readonly import write_readonly_record
from siftmesh_core.ledgers.claim_ledger import read_claims, read_unsupported_claims
from siftmesh_core.ledgers.tool_call_ledger import read_tool_results
from siftmesh_core.mcp_gateway.server import build_server
from siftmesh_core.mcp_gateway.tools.validation_tools import _manifest_hashes
from siftmesh_core.orchestrator.critic import critique_run
from siftmesh_core.run_dir import RunPaths, new_run_dir
from siftmesh_core.schemas.task import InputArtifact, SafetyPolicy, TaskContract


def _contract() -> TaskContract:
    return TaskContract(
        task_id="TASK-001",
        role="hash_executor",
        objective="Establish the evidence hash baseline",
        assigned_agent_profile="claude_headless",
        allowed_tools=["compute_hash_manifest"],
        input_artifacts=[InputArtifact(path="artifact.bin", sha256="a" * 64)],
        safety_policy=SafetyPolicy(),
    )


def _ctx(
    run: RunPaths, evidence: Path, *, attempt: int, feedback: tuple[str, ...] = ()
) -> AdapterContext:
    return AdapterContext(
        run=run,
        evidence_root=evidence,
        settings=load_settings(),
        attempt=attempt,
        requested_profile="claude_headless",
        critic_feedback=feedback,
    )


# ── unit: claim capture ───────────────────────────────────────────────────────


def _parse(raw_text: str, *, attempt: int = 1, tmp: Path) -> object:
    run = new_run_dir(base=tmp / "case_runs")
    started = datetime.now(UTC)
    return parse_agent_result(
        raw_text,
        contract=_contract(),
        ctx=_ctx(run, tmp, attempt=attempt),
        adapter_id="claude_headless",
        started=started,
        ended=datetime.now(UTC),
    )


def test_capture_anchored_claim(tmp_path: Path) -> None:
    payload = json.dumps(
        {
            "claims": [
                {
                    "claim": "baseline established",
                    "status": "confirmed",
                    "confidence": 0.8,
                    "evidence_type": "hash",
                    "source_artifact": "artifact.bin",
                    "source_sha256": "b" * 64,
                    "tool_name": "compute_hash_manifest",
                    "tool_call_id": "TOOL-001",
                    "supporting_evidence_refs": ["TOOL-001"],
                }
            ]
        }
    )
    result = _parse(payload, tmp=tmp_path)
    assert result.status == "success"
    assert len(result.claims) == 1 and result.claims[0].status == "confirmed"
    assert result.claims[0].claim_id == "TASK-001-A1-CLAIM-001"  # attempt-scoped


def test_under_anchored_claim_recorded_unsupported_not_fabricated(tmp_path: Path) -> None:
    # status says 'confirmed' but no sha / tool_call_id -> NEVER invent one; record as unsupported.
    payload = json.dumps(
        {"claims": [{"claim": "X happened", "status": "confirmed", "confidence": 0.9}]}
    )
    result = _parse(payload, tmp=tmp_path)
    assert result.status == "success"  # adapter captured the output; critic governs truth
    assert result.claims[0].status == "unsupported"
    assert result.claims[0].source_sha256 is None  # not fabricated


def test_unparseable_output_is_retry_required(tmp_path: Path) -> None:
    result = _parse("I could not complete the task.", tmp=tmp_path)
    assert result.status == "retry_required"
    assert result.retry_cause == "agent_output_not_parseable_as_claims"


def test_empty_claims_is_retry_required(tmp_path: Path) -> None:
    result = _parse(json.dumps({"claims": []}), tmp=tmp_path)
    assert result.status == "retry_required"
    assert result.retry_cause == "agent_produced_no_claims"


# ── headline: end-to-end emergent self-correction (real critic, mocked agent) ──


def _substrate(tmp_path: Path) -> tuple[RunPaths, Path]:
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    (evidence / "artifact.bin").write_bytes(b"real evidence bytes for the baseline")
    run = new_run_dir(base=tmp_path / "case_runs")
    manifest = build_manifest_from_dir(evidence, case_id="case01", run_id=run.run_id)
    write_manifest(manifest, run.root, evidence_root=evidence)
    write_readonly_record(evidence, run.root, file_count=len(manifest.files))
    return run, evidence


def _seed_real_tool_call(run: RunPaths, evidence: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """Run a REAL typed tool so a genuine tool_call_id + manifest hash exist to anchor against."""
    monkeypatch.setenv("SIFTMESH_RUN_ROOT", str(run.root))
    monkeypatch.setenv("SIFTMESH_EVIDENCE_ROOT", str(evidence))
    asyncio.run(build_server().call_tool("compute_hash_manifest", {}))
    return read_tool_results(run.root)[-1].tool_call_id


def test_emergent_self_correction_loop(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run, evidence = _substrate(tmp_path)
    tcid = _seed_real_tool_call(run, evidence, monkeypatch)
    artifact, sha = next(iter(_manifest_hashes(run.root).items()))  # real anchor

    anchored = {
        "claims": [
            {
                "claim": "evidence hash baseline established",
                "status": "confirmed",
                "confidence": 0.85,
                "evidence_type": "hash",
                "source_artifact": artifact,
                "source_sha256": sha,
                "tool_name": "compute_hash_manifest",
                "tool_call_id": tcid,
                "supporting_evidence_refs": [tcid],
            }
        ]
    }
    unanchored = {  # over-claims with NO sha / tool_call_id -> will be recorded 'unsupported'
        "claims": [
            {
                "claim": "evidence hash baseline established",
                "status": "confirmed",
                "confidence": 0.85,
                "evidence_type": "hash",
                "source_artifact": artifact,
            }
        ]
    }

    def fake_run(*args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        argv = args[0]
        prompt = argv[argv.index("-p") + 1]  # type: ignore[union-attr,index]
        revised = "PREVIOUS ATTEMPT WAS REJECTED" in prompt  # agent reacts to critic feedback
        result_text = json.dumps(anchored if revised else unanchored)
        envelope = json.dumps({"result": result_text, "is_error": False, "session_id": "s"})
        return subprocess.CompletedProcess(args=[], returncode=0, stdout=envelope, stderr="")

    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "sub-token")
    monkeypatch.setattr(subprocess, "run", fake_run)
    adapter = ClaudeHeadlessAdapter(settings=load_settings())
    contract = _contract()

    # Attempt 1 - no feedback -> agent under-anchors -> critic rejects.
    adapter.run(contract, _ctx(run, evidence, attempt=1))
    v1 = critique_run(run, settings=load_settings(), evidence_root=evidence)
    task_v1 = next(v for v in v1 if v.task_id == "TASK-001")
    assert task_v1.verdict == "retry_required"
    assert read_unsupported_claims(run.root)  # the over-claim recorded honestly...
    assert not [c for c in read_claims(run.root) if c.status == "confirmed"]  # ...not as a finding

    # Attempt 2 - critic feedback flows into the prompt -> agent revises with a real anchor.
    adapter.run(contract, _ctx(run, evidence, attempt=2, feedback=tuple(task_v1.reasons)))
    v2 = critique_run(run, settings=load_settings(), evidence_root=evidence)
    task_v2 = next(v for v in v2 if v.task_id == "TASK-001")
    assert task_v2.verdict in ("accepted", "accepted_with_downgrade")
    confirmed = [c for c in read_claims(run.root) if c.status == "confirmed"]
    assert confirmed and confirmed[0].tool_call_id == tcid  # corrected claim is report-eligible
    assert read_unsupported_claims(run.root)  # the rejected over-claim still only in its own ledger
