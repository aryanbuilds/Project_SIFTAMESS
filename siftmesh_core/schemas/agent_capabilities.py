"""Agent capability-map schema (Epic Q onboarding).

The typed, validated map that ``siftmesh doctor --agents`` / ``siftmesh agents list`` produce and
(optionally) write to ``context/agent_capabilities.json``. It is an honest, env-only snapshot of
which coding-agent CLIs are installed + authenticated on this host, whether each can reach the typed
forensic tools, and which one SIFTMesh would pick as the live default. No timestamp field — the map
is a pure function of the host + profiles, so it is fully snapshot-stable (``StrictModel`` — a map
that fails validation is never written).
"""

from __future__ import annotations

from pydantic import Field

from siftmesh_core.schemas._base import StrictModel

# How an agent reaches SIFTMesh's typed forensic tools (honest; only Claude is verified today).
ToolReachability = ("yes", "no", "verify-live")


class AgentCapability(StrictModel):
    """One coding-agent connector's onboarding status on this host."""

    profile_id: str
    kind: str  # "claude" | "opencode" | "headless" | "deterministic"
    present: bool  # the CLI is on PATH
    version: str  # `--version` first line, or "absent" / "unknown"
    auth_ok: bool  # an auth env var is set / cached credentials exist (or none required)
    sandboxed: bool  # native agent tools are denied (REQUIRED to dispatch; honest evidence-safety)
    tool_reachable: str  # one of ToolReachability — can it reach the typed MCP tools?
    selected: bool  # SIFTMesh would dispatch to this profile by default IN THIS CONFIG


class AgentCapabilityMap(StrictModel):
    """Validated onboarding map: every connector's status + the dispatch default + the opt-in."""

    agents: list[AgentCapability] = Field(default_factory=list)  # sorted by profile_id
    chosen: str  # what a plain `siftmesh run` dispatches in THIS config (honors executor_selection)
    live_candidate: str | None = None  # best ready live agent to opt into via `--agent` (if any)
