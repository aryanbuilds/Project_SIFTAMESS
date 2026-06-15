"""L5i - bypass test: repudiation & untraceability (OWASP Agentic ASI-T8) - a SIFTMesh STRENGTH.

Untraceability is a named agentic threat; SIFTMesh's audit ledgers + per-claim tool-call anchoring
are the MITIGATION, so it should be a TESTED guarantee, not an unspoken assumption. Asserts: every
tool call in audit/tool_calls.jsonl carries provenance (tool_call_id / source_sha256 / start+end
UTC / status), and every promoted claim resolves to a real tool_call_id in that ledger - so any
finding in the report traces back to the exact bytes a real tool parsed ("replayable audit").
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from siftmesh_core.ledgers.claim_ledger import read_claims
from siftmesh_core.ledgers.tool_call_ledger import read_tool_results
from siftmesh_core.run_dir import RunPaths

DispatchedCase = Callable[..., tuple[RunPaths, Path]]


def test_every_tool_call_has_full_provenance(dispatched_case: DispatchedCase) -> None:
    run, _ = dispatched_case()
    results = read_tool_results(run.root)
    assert results, "precondition: real tools executed and were audited"
    for tr in results:
        assert tr.tool_call_id
        assert len(tr.source_sha256) == 64  # exact bytes parsed
        assert tr.start_time_utc and tr.end_time_utc
        assert tr.status
        assert tr.tool_name


def test_every_promoted_claim_resolves_to_a_real_tool_call(dispatched_case: DispatchedCase) -> None:
    run, _ = dispatched_case()
    tool_ids = {tr.tool_call_id for tr in read_tool_results(run.root)}
    claims = read_claims(run.root)
    assert claims, "precondition: promoted claims exist"
    for c in claims:
        assert c.tool_call_id is not None, c.claim_id  # promoted claims are always anchored
        assert c.tool_call_id in tool_ids, f"{c.claim_id} anchors a non-existent tool call"
