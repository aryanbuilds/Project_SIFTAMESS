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

# Honest safety-tier model (labels only — it never gates dispatch). Derived purely from the existing
# capability booleans so the label can never disagree with what actually runs:
#   T0 — the deterministic real-tool floor (no LLM tool execution; the safe default).
#   T1 — a live executor that is sandboxed AND reaches the typed tools through the strict-MCP
#        boundary (today: only claude_headless).
#   T2 — a live executor that is NOT T1 (unsandboxed, or tool-reach unproven/native). Capable but
#        unconstrained; an explicit `--agent` opt-in — never described as sandboxed.
#   T3 — the advisory Tier-2 judge backends (tool-less; may only lower confidence / annotate).
#        Not an executor tier; surfaced on the judge line, not per-agent in the capability map.
SAFETY_TIERS = ("T0", "T1", "T2", "T3")
SAFETY_TIER_DESC: dict[str, str] = {
    "T0": "deterministic_floor — real tools, no LLM execution (safe default)",
    "T1": "constrained_live — sandboxed + typed tools via strict-MCP",
    "T2": "unconstrained_live — capable but unsandboxed/unproven tool reach (explicit opt-in)",
    "T3": "advisory_llm — tool-less Tier-2 judge (never promotes; may only downgrade/annotate)",
}


def safety_tier_label(tier: str) -> str:
    """``"T2"`` -> ``"T2 unconstrained_live — …"`` (shared by CLI / TUI / docs)."""
    desc = SAFETY_TIER_DESC.get(tier)
    return f"{tier} {desc}" if desc else tier


class AgentCapability(StrictModel):
    """One coding-agent connector's onboarding status on this host."""

    profile_id: str
    kind: str  # "claude" | "opencode" | "headless" | "deterministic"
    present: bool  # the CLI is on PATH
    version: str  # `--version` first line, or "absent" / "unknown"
    auth_ok: bool  # an auth env var is set / cached credentials exist (or none required)
    sandboxed: bool  # native agent tools are denied (REQUIRED to dispatch; honest evidence-safety)
    tool_reachable: str  # one of ToolReachability — can it reach the typed MCP tools?
    safety_tier: str = "T2"  # one of SAFETY_TIERS — honest containment label (never gates dispatch)
    selected: bool  # SIFTMesh would dispatch to this profile by default IN THIS CONFIG


class AgentCapabilityMap(StrictModel):
    """Validated onboarding map: every connector's status + the dispatch default + the opt-in."""

    agents: list[AgentCapability] = Field(default_factory=list)  # sorted by profile_id
    chosen: str  # what a plain `siftmesh run` dispatches in THIS config (honors executor_selection)
    live_candidate: str | None = None  # best ready live agent to opt into via `--agent` (if any)
