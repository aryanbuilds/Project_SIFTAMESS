"""Epic D FastMCP server wiring + allowlist enforcement (D1, D10)."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from siftmesh_core.mcp_gateway.registry import ALLOWED_TOOLS, FORBIDDEN_TOOLS, assert_tool_allowed
from siftmesh_core.mcp_gateway.server import build_server, registered_tool_names, tool_adapters
from siftmesh_core.run_dir import new_run_dir


def test_adapters_cover_exactly_the_allowlist() -> None:
    assert set(tool_adapters()) == set(ALLOWED_TOOLS)


def test_server_registers_exactly_the_allowlisted_tools() -> None:
    mcp = build_server()
    assert registered_tool_names(mcp) == set(ALLOWED_TOOLS)
    assert registered_tool_names(mcp).isdisjoint(FORBIDDEN_TOOLS)


def test_forbidden_tool_cannot_be_registered() -> None:
    # The same guard build_server() applies to every name.
    for name in FORBIDDEN_TOOLS:
        with pytest.raises(Exception, match="forbidden"):
            assert_tool_allowed(name)


def test_server_call_tool_executes_end_to_end(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    (evidence / "a.bin").write_bytes(b"real-bytes")
    run = new_run_dir(base=tmp_path / "case_runs")

    mcp = build_server()
    result = asyncio.run(
        mcp.call_tool(
            "compute_hash_manifest",
            {"run_root": str(run.root), "evidence_root": str(evidence)},
        )
    )
    # FastMCP returns (content_blocks, structured_result); the tool succeeded if the
    # provenance line was written under the run dir.
    assert result is not None
    tool_calls = (run.root / "audit" / "tool_calls.jsonl").read_text().splitlines()
    assert len(tool_calls) == 1
    assert '"status":"success"' in tool_calls[0].replace(" ", "")
