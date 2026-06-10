"""L5g — bypass test: MCP confused-deputy & single-server surface (threat T2 · LLM03 · ASI02/ASI03).

The 2025 MCP attack families (tool poisoning / line-jumping / cross-server shadowing / rug-pull /
confused-deputy) are designed out by construction. This asserts the EFFECTS: (1) the agent-facing
tools take ONLY artifact args — none accepts a run/evidence root, so a hostile prompt can't redirect
a tool at another case; (2) the server fails CLOSED when its run scope is unset; (3) a tool-arg path
escaping the trusted roots is rejected; (4) exactly one first-party stdio server is configured, with
--strict-mcp-config (no ambient server to shadow). Stdio-only => no OAuth/session/SSRF surface.
"""

from __future__ import annotations

import inspect
import json
from collections.abc import Callable
from pathlib import Path

import pytest
from siftmesh_core.adapters.base import AdapterContext
from siftmesh_core.adapters.claude_adapter import ClaudeHeadlessAdapter, _build_claude_argv
from siftmesh_core.config import load_settings
from siftmesh_core.mcp_gateway.server import _parse_evtx_security, _run_scope, tool_adapters
from siftmesh_core.run_dir import RunPaths

DispatchedCase = Callable[..., tuple[RunPaths, Path]]
_ROOT_PARAMS = {"run_root", "evidence_root", "root", "case_root", "base"}


def test_no_tool_adapter_accepts_a_root_param() -> None:
    # Confused-deputy designed out: the agent literally cannot pass a run/evidence root.
    for name, adapter in tool_adapters().items():
        params = set(inspect.signature(adapter).parameters)
        assert params.isdisjoint(_ROOT_PARAMS), (
            f"{name} exposes a root param: {params & _ROOT_PARAMS}"
        )


def test_run_scope_fails_closed_when_unset(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.delenv("SIFTMESH_RUN_ROOT", raising=False)
    monkeypatch.delenv("SIFTMESH_EVIDENCE_ROOT", raising=False)
    with pytest.raises(RuntimeError, match="must be set by the dispatching adapter"):
        _run_scope()


def test_tool_arg_path_escape_rejected(dispatched_case: DispatchedCase, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    run, evidence = dispatched_case(dispatch=False)
    monkeypatch.setenv("SIFTMESH_RUN_ROOT", str(Path(run.root).resolve()))
    monkeypatch.setenv("SIFTMESH_EVIDENCE_ROOT", str(Path(evidence).resolve()))
    # A hostile source_artifact arg cannot escape the trusted roots (resolved_source containment).
    with pytest.raises(ValueError, match="escapes evidence root"):
        _parse_evtx_security("../../../etc/passwd")


def test_exactly_one_first_party_server_strict(dispatched_case: DispatchedCase) -> None:
    run, evidence = dispatched_case(dispatch=False)
    adapter = ClaudeHeadlessAdapter(settings=load_settings())
    ctx = AdapterContext(run=run, evidence_root=evidence, settings=load_settings())
    cfg = json.loads(adapter._write_mcp_config(ctx).read_text(encoding="utf-8"))
    assert set(cfg["mcpServers"]) == {"siftmesh"}  # no second server to shadow / name-collide
    argv = _build_claude_argv("claude", "x", Path("/tmp/mcp.json"), ["parse_evtx_security"])
    assert "--strict-mcp-config" in argv  # ambient/global MCP servers are ignored
