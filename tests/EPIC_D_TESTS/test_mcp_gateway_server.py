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


def test_server_call_tool_executes_end_to_end(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    (evidence / "a.bin").write_bytes(b"real-bytes")
    run = new_run_dir(base=tmp_path / "case_runs")
    # K3: roots come from the adapter-set environment, NOT from agent-supplied args.
    monkeypatch.setenv("SIFTMESH_RUN_ROOT", str(run.root))
    monkeypatch.setenv("SIFTMESH_EVIDENCE_ROOT", str(evidence))

    mcp = build_server()
    result = asyncio.run(mcp.call_tool("compute_hash_manifest", {}))  # no roots in the call
    # FastMCP returns (content_blocks, structured_result); the tool succeeded if the
    # provenance line was written under the run dir.
    assert result is not None
    tool_calls = (run.root / "audit" / "tool_calls.jsonl").read_text().splitlines()
    assert len(tool_calls) == 1
    assert '"status":"success"' in tool_calls[0].replace(" ", "")


def test_agent_facing_signature_drops_roots() -> None:
    # K3: the agent supplies only artifact args; it can never choose the run/evidence root.
    mcp = build_server()
    tools = {tool.name: tool for tool in mcp._tool_manager.list_tools()}
    props = tools["parse_evtx_security"].parameters.get("properties", {})
    assert "run_root" not in props and "evidence_root" not in props
    assert "source_artifact" in props


def test_unscoped_tool_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    from siftmesh_core.mcp_gateway.server import _compute_hash_manifest, _run_scope

    monkeypatch.delenv("SIFTMESH_RUN_ROOT", raising=False)
    monkeypatch.delenv("SIFTMESH_EVIDENCE_ROOT", raising=False)
    with pytest.raises(RuntimeError, match="unscoped"):
        _run_scope()
    with pytest.raises(RuntimeError):
        _compute_hash_manifest()  # missing env => refuse, never guess a root
