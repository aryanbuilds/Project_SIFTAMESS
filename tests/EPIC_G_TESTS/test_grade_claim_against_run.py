"""G2 - grade_claim_against_run matches the D9 tool and writes no tool_calls line."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from siftmesh_core.ledgers.tool_call_ledger import read_tool_results
from siftmesh_core.mcp_gateway.tools.validation_tools import (
    grade_claim_against_run,
    validate_claim_evidence,
)
from siftmesh_core.run_dir import RunPaths
from siftmesh_core.schemas.claim import Claim

DispatchedCase = Callable[..., tuple[RunPaths, Path]]


def _a_real_claim(run: RunPaths) -> Claim:
    from siftmesh_core.ledgers.claim_ledger import read_claims

    return read_claims(run.root)[0]


def test_grader_matches_d9_tool_and_writes_no_tool_line(dispatched_case: DispatchedCase) -> None:
    run, evidence = dispatched_case()
    claim = _a_real_claim(run)
    before = len(read_tool_results(run.root))
    problems = grade_claim_against_run(run.root, claim, evidence_root=evidence)
    after_grader = len(read_tool_results(run.root))
    tool_result = validate_claim_evidence(run.root, claim, evidence_root=evidence)
    # same verdict...
    assert problems == tool_result.problems
    # ...but the direct grader appended NO tool_calls line (the D9 tool appended one)
    assert after_grader == before
    assert len(read_tool_results(run.root)) == before + 1


def test_grader_flags_unknown_tool_call_id(dispatched_case: DispatchedCase) -> None:
    run, evidence = dispatched_case()
    claim = _a_real_claim(run).model_copy(update={"tool_call_id": "TOOL-999"})
    problems = grade_claim_against_run(run.root, claim, evidence_root=evidence)
    assert any("tool_call_id" in p for p in problems)
