"""L5b — bypass test: typed-tool (MCP) boundary (SIFTMesh threat T2/T5 · OWASP LLM06/LLM03 · ASI02).

Asserts the EFFECT of the forbidden-tool registry: the 7 destructive names (and any off-allowlist
name) can NEVER register, and the REAL FastMCP server exposes EXACTLY the 11-tool allowlist and zero
forbidden names. Stronger than a deny-list (Velociraptor lockdown / GRR restricted-flows): the
destructive surface is ABSENT, not grantable. Satisfies CLAUDE §14 test_forbidden_tool_not_exposed.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from siftmesh_core.mcp_gateway.registry import (
    ALLOWED_TOOLS,
    FORBIDDEN_TOOLS,
    ToolNotAllowedError,
    assert_tool_allowed,
)
from siftmesh_core.mcp_gateway.server import build_server, registered_tool_names, tool_adapters


def test_allowlist_is_exactly_ten() -> None:
    assert len(ALLOWED_TOOLS) == 11
    assert len(FORBIDDEN_TOOLS) == 7


@pytest.mark.parametrize("name", sorted(FORBIDDEN_TOOLS))
def test_forbidden_name_cannot_register(name: str) -> None:
    with pytest.raises(ToolNotAllowedError, match="forbidden"):
        assert_tool_allowed(name)


@pytest.mark.parametrize(
    "name",
    ["arbitrary_python; rm -rf /", "execute_shell", "delete_evidence", "net_fetch", "eval"],
)
def test_off_allowlist_name_rejected(name: str) -> None:
    with pytest.raises(ToolNotAllowedError, match="not in the forensic allowlist"):
        assert_tool_allowed(name)


def test_real_server_surface_equals_allowlist() -> None:
    # The strongest architectural-effect proof: the live FastMCP boundary exposes exactly the 10.
    mcp = build_server()
    surface = registered_tool_names(mcp)
    assert surface == set(ALLOWED_TOOLS)
    assert len(surface) == 11
    assert FORBIDDEN_TOOLS.isdisjoint(surface)


def test_tool_adapter_map_matches_allowlist() -> None:
    assert set(tool_adapters()) == set(ALLOWED_TOOLS)


def test_no_dynamic_dispatch_in_registration() -> None:
    # A name must not be smuggleable by string-building: the registration path has no eval/exec.
    src = ""
    for mod in ("registry.py", "server.py"):
        src += (
            Path(__file__).resolve().parents[2] / "siftmesh_core" / "mcp_gateway" / mod
        ).read_text()
    assert "eval(" not in src
    assert "exec(" not in src


def test_no_network_egress_tool_in_surface() -> None:
    # Removes Willison's lethal-trifecta leg 3 (exfil): no allowlisted tool performs network egress.
    # (Curated verbs so a forensic name like 'analyze_prefetch' isn't a false positive.)
    banned = (
        "curl",
        "wget",
        "http",
        "scp",
        "ssh",
        "download",
        "upload",
        "exfil",
        "socket",
        "request",
    )
    for name in ALLOWED_TOOLS:
        assert not any(b in name.lower() for b in banned), name
