"""Epic D gateway core: allowlist, audited provenance, backends, validation (D1-D4, D9)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from siftmesh_core.evidence.manifest import build_manifest_from_dir, write_manifest
from siftmesh_core.ledgers.tool_call_ledger import read_tool_results
from siftmesh_core.mcp_gateway.audit_exec import run_tool
from siftmesh_core.mcp_gateway.backends import BackendUnavailableError, get_backend
from siftmesh_core.mcp_gateway.registry import (
    ALLOWED_TOOLS,
    FORBIDDEN_TOOLS,
    ToolNotAllowedError,
    assert_tool_allowed,
)
from siftmesh_core.mcp_gateway.tools.evidence_tools import (
    HashManifestResult,
    compute_hash_manifest,
    create_readonly_evidence_vault,
)
from siftmesh_core.mcp_gateway.tools.validation_tools import validate_claim_evidence
from siftmesh_core.run_dir import RunPaths, new_run_dir
from siftmesh_core.schemas.claim import Claim


def _case(tmp_path: Path) -> tuple[RunPaths, Path]:
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    (evidence / "a.evtx").write_bytes(b"unit-test-fixture-bytes")
    run = new_run_dir(base=tmp_path / "case_runs")
    return run, evidence


def test_allowlist_is_exactly_the_ten_tools() -> None:
    # The original 8 (§7) plus governed expansions (image + memory + the P0 deep-evidence tools).
    assert len(ALLOWED_TOOLS) == 16
    assert "validate_claim_evidence" in ALLOWED_TOOLS
    assert {"extract_artifacts_from_image", "analyze_memory"} <= ALLOWED_TOOLS
    assert {"parse_browser_history", "parse_lnk_jumplists", "parse_shellbags"} <= ALLOWED_TOOLS


def test_forbidden_tool_not_exposed() -> None:
    for name in FORBIDDEN_TOOLS:
        with pytest.raises(ToolNotAllowedError):
            assert_tool_allowed(name)
    assert FORBIDDEN_TOOLS.isdisjoint(ALLOWED_TOOLS)


def test_unknown_tool_rejected() -> None:
    with pytest.raises(ToolNotAllowedError):
        assert_tool_allowed("definitely_not_a_real_tool")


def test_real_backend_selected_by_default() -> None:
    assert get_backend("real").name == "real"
    assert get_backend("auto").name == "real"


def test_sift_lane_backend_selected() -> None:
    assert get_backend("sift_lane").name == "sift_lane"


def test_sift_lane_fails_closed_when_ez_tools_absent(tmp_path: Path) -> None:
    # D12 is wired, but a missing EZ Tool DLL still fails closed (never fakes).
    from siftmesh_core.mcp_gateway.backends.sift_lane import SiftLaneBackend

    backend = SiftLaneBackend(ez_tools_dir=tmp_path / "no_ez_tools")
    for call in (
        lambda: backend.parse_evtx(Path("x.evtx")),
        lambda: backend.parse_mft(Path("x")),
        lambda: backend.extract_run_keys(Path("x")),
    ):
        with pytest.raises(BackendUnavailableError):
            call()


def test_sift_lane_prefetch_always_fails_closed() -> None:
    # PECmd is not part of the EZ Tools set — prefetch fails closed regardless of host.
    from siftmesh_core.mcp_gateway.backends.sift_lane import SiftLaneBackend

    with pytest.raises(BackendUnavailableError):
        SiftLaneBackend().analyze_prefetch(Path("x.pf"))


def test_unknown_backend_mode_rejected() -> None:
    with pytest.raises(ValueError, match="unknown backend mode"):
        get_backend("nope")


def test_tool_call_logged_with_full_provenance(tmp_path: Path) -> None:
    run, evidence = _case(tmp_path)
    result = compute_hash_manifest(run.root, evidence_root=evidence)

    assert result.status == "success"
    assert result.tool_call_id == "TOOL-001"
    assert result.file_count == 1
    assert result.backend == "real"

    ledger = read_tool_results(run.root)
    assert len(ledger) == 1
    rec = ledger[0]
    assert rec.tool_call_id == "TOOL-001"
    assert len(rec.source_sha256) == 64
    assert rec.tool_version and rec.start_time_utc <= rec.end_time_utc
    assert rec.structured_result_path == "results/TOOL-001.structured.json"


def test_structured_output_and_derived_under_run_dir(tmp_path: Path) -> None:
    run, evidence = _case(tmp_path)
    result = compute_hash_manifest(run.root, evidence_root=evidence)

    structured = run.root / str(result.structured_result_path)
    assert structured.is_file()
    assert structured.resolve().is_relative_to(run.root.resolve())  # path policy
    payload = json.loads(structured.read_text())
    assert payload["file_count"] == 1

    derived = json.loads((run.root / "evidence" / "derived_artifacts.json").read_text())
    assert derived["derived"][0]["tool_call_id"] == "TOOL-001"

    custody = (run.root / "evidence" / "custody_log.jsonl").read_text().splitlines()
    assert any('"tool_invoked"' in line for line in custody)


def test_deterministic_sequential_tool_ids(tmp_path: Path) -> None:
    run, evidence = _case(tmp_path)
    first = compute_hash_manifest(run.root, evidence_root=evidence)
    second = create_readonly_evidence_vault(run.root, evidence_root=evidence)
    assert (first.tool_call_id, second.tool_call_id) == ("TOOL-001", "TOOL-002")
    assert second.enforcement == "posture_only"
    assert (run.root / "evidence" / "readonly_mounts.json").is_file()


def test_invalid_structured_payload_is_not_persisted(tmp_path: Path) -> None:
    run, evidence = _case(tmp_path)
    with pytest.raises(ValidationError):
        run_tool(
            run.root,
            result_cls=HashManifestResult,
            tool_name="compute_hash_manifest",
            source_artifact=".",
            source_sha256="0" * 64,
            backend="real",
            produce=lambda: {"unexpected": True},
            evidence_root=evidence,
        )
    assert not (run.root / "audit" / "tool_calls.jsonl").exists()
    assert not (run.root / "results" / "TOOL-001.structured.json").exists()


def _manifest(run: RunPaths, evidence: Path) -> str:
    manifest = build_manifest_from_dir(evidence, case_id="c", run_id=run.run_id)
    write_manifest(manifest, run.root, evidence_root=evidence)
    return manifest.files[0].sha256


def test_validate_claim_evidence_accepts_anchored_claim(tmp_path: Path) -> None:
    run, evidence = _case(tmp_path)
    sha = _manifest(run, evidence)
    compute_hash_manifest(run.root, evidence_root=evidence)  # creates TOOL-001
    claim = Claim(
        claim_id="CLAIM-1",
        task_id="T",
        status="confirmed",
        claim="a logon event was observed",
        confidence=0.9,
        evidence_type="event_log",
        source_artifact="a.evtx",
        source_sha256=sha,
        tool_name="parse_evtx_security",
        tool_call_id="TOOL-001",
    )
    result = validate_claim_evidence(run.root, claim, evidence_root=evidence)
    assert result.valid is True
    assert result.problems == []
    assert result.checked_claim_id == "CLAIM-1"


def test_validate_claim_evidence_rejects_bad_hash(tmp_path: Path) -> None:
    run, evidence = _case(tmp_path)
    _manifest(run, evidence)
    compute_hash_manifest(run.root, evidence_root=evidence)
    claim = Claim(
        claim_id="CLAIM-2",
        task_id="T",
        status="confirmed",
        claim="x",
        confidence=0.5,
        evidence_type="event_log",
        source_artifact="a.evtx",
        source_sha256="f" * 64,
        tool_name="t",
        tool_call_id="TOOL-001",
    )
    result = validate_claim_evidence(run.root, claim, evidence_root=evidence)
    assert result.valid is False
    assert any("mismatch" in p for p in result.problems)


def test_validate_claim_evidence_grades_raw_malformed_claim(tmp_path: Path) -> None:
    run, evidence = _case(tmp_path)
    _manifest(run, evidence)
    # Raw mapping missing tool_call_id — must be graded, not rejected at parse time.
    raw = {
        "claim_id": "CLAIM-3",
        "task_id": "T",
        "status": "confirmed",
        "claim": "x",
        "confidence": 0.5,
        "evidence_type": "event_log",
        "source_artifact": "a.evtx",
    }
    result = validate_claim_evidence(run.root, raw, evidence_root=evidence)
    assert result.valid is False
    assert any("tool_call_id" in p for p in result.problems)


def test_validate_unsupported_claim_is_clean(tmp_path: Path) -> None:
    run, evidence = _case(tmp_path)
    _manifest(run, evidence)
    claim = Claim(
        claim_id="CLAIM-4",
        task_id="T",
        status="unsupported",
        claim="attacker used a VPN (no artifact)",
        confidence=0.1,
        evidence_type="none",
    )
    result = validate_claim_evidence(run.root, claim, evidence_root=evidence)
    assert result.valid is True
    assert result.problems == []
