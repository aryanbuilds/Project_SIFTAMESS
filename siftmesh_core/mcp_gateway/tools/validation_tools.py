"""Validation tool (D9) — the deterministic claim-evidence verifier (differentiator).

``validate_claim_evidence`` is the primitive the Critic (Epic G) consumes. Given a
:class:`Claim` *or a raw mapping* (so malformed agent output can be graded, not
rejected at parse time), it checks evidence discipline three ways against the run's
own ledgers: (1) schema-level anchoring (the C2 grader), (2) ``source_artifact`` is
in the evidence manifest and ``source_sha256`` matches it, and (3) ``tool_call_id``
exists in ``audit/tool_calls.jsonl``. Pure-Python, always-real; the call itself is
logged with provenance (the claim under test is the source).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pydantic import Field

from siftmesh_core import __version__
from siftmesh_core.ledgers.tool_call_ledger import read_tool_results
from siftmesh_core.mcp_gateway.audit_exec import run_tool
from siftmesh_core.schemas.claim import Claim
from siftmesh_core.schemas.claim import validate_claim_evidence as grade_claim_schema
from siftmesh_core.schemas.evidence import EvidenceManifest
from siftmesh_core.schemas.tool_result import ToolResult


class ClaimValidationResult(ToolResult):
    """``validate_claim_evidence`` output: verdict + the specific violations found."""

    checked_claim_id: str | None = None
    valid: bool = False
    problems: list[str] = Field(default_factory=list)


def _manifest_hashes(run_root: Path | str) -> dict[str, str]:
    """Map evidence-relative path -> sha256 from the run's manifest (empty if none)."""
    path = Path(run_root) / "evidence" / "evidence_manifest.json"
    if not path.exists():
        return {}
    manifest = EvidenceManifest.model_validate_json(path.read_text(encoding="utf-8"))
    return {f.path: f.sha256 for f in manifest.files}


def _field(claim: Claim | Mapping[str, Any], name: str) -> Any:
    """Read a field from a Claim or a raw mapping (the Critic grades both)."""
    return getattr(claim, name) if isinstance(claim, Claim) else claim.get(name)


def grade_claim_against_run(
    run_root: Path | str,
    claim: Claim | Mapping[str, Any],
    *,
    evidence_root: Path | str | None = None,
) -> list[str]:
    """Evidence-discipline violations for a claim vs the run's manifest + tool ledger.

    Empty list = clean. This is the **non-audited** core the D9 tool wraps — the
    Critic (Epic G) calls it directly per claim so grading does NOT spam
    ``tool_calls.jsonl`` with a TOOL-NNN per claim. ``evidence_root`` is accepted for
    signature parity (the manifest already lives under the run dir).
    """
    problems = list(grade_claim_schema(claim))  # C2 grader: accepts Claim or mapping
    if _field(claim, "status") != "unsupported":
        hashes = _manifest_hashes(run_root)
        results = {r.tool_call_id: r for r in read_tool_results(run_root)}
        artifact = _field(claim, "source_artifact")
        source_sha256 = _field(claim, "source_sha256")
        tool_call_id = _field(claim, "tool_call_id")
        if artifact is not None:
            if artifact in hashes:
                # chain of custody to an original evidence artifact
                if source_sha256 and hashes[artifact] != source_sha256:
                    problems.append(f"source_sha256 mismatch for {artifact}")
            else:
                # a derived/aggregate source (e.g. build_timeline's "timeline") must match
                # the provenance recorded by its own audited tool call.
                tr = results.get(tool_call_id) if tool_call_id is not None else None
                if tr is None:
                    problems.append(f"source_artifact not in evidence manifest: {artifact}")
                elif artifact != tr.source_artifact:
                    problems.append(
                        f"source_artifact {artifact!r} not in manifest and not produced "
                        f"by {tool_call_id}"
                    )
                elif source_sha256 and tr.source_sha256 != source_sha256:
                    problems.append(f"source_sha256 mismatch for derived {artifact}")
        if tool_call_id is not None and tool_call_id not in results:
            problems.append(f"tool_call_id not found in audit: {tool_call_id}")
    return problems


def validate_claim_evidence(
    run_root: Path | str,
    claim: Claim | Mapping[str, Any],
    *,
    evidence_root: Path | str | None = None,
) -> ClaimValidationResult:
    """Verify a claim's evidence anchor against the run's manifest + tool ledger."""
    if isinstance(claim, Claim):
        digest_src = claim.model_dump_json()
    else:
        digest_src = json.dumps(dict(claim), sort_keys=True, default=str)
    claim_digest = hashlib.sha256(digest_src.encode("utf-8")).hexdigest()
    claim_id = _field(claim, "claim_id") or "<unknown>"

    def produce() -> dict[str, Any]:
        problems = grade_claim_against_run(run_root, claim, evidence_root=evidence_root)
        return {"checked_claim_id": claim_id, "valid": not problems, "problems": problems}

    return run_tool(
        run_root,
        result_cls=ClaimValidationResult,
        tool_name="validate_claim_evidence",
        source_artifact=f"claim:{claim_id}",
        source_sha256=claim_digest,
        backend="real",
        tool_version=__version__,
        produce=produce,
        evidence_root=evidence_root,
    )
