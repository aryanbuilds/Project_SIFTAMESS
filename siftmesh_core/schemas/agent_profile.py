"""Agent-profile schema (C5 + Epic I) — a dispatchable agent's identity, cost, and wiring.

``kind`` enumerates the adapter families SIFTMesh drives; ``model_tier`` / ``cost_class`` feed the
Budget Router; ``output_format`` tells the collector how to read the result; ``command_template`` /
``model`` / ``max_runtime_seconds`` parameterise the (human-gated) live invocation. The profile
registry (``adapters/profiles.py`` + ``agent_profiles.yaml``) is Epic I.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from siftmesh_core.schemas._base import StrictModel

ModelTier = Literal["high", "low", "local"]
CostClass = Literal["expensive", "cheap", "free"]
# The adapter families SIFTMesh can dispatch to (must map to a registered adapter profile_id).
# ``headless`` = the config-driven, agent-neutral one-shot connector (Epic Q): launch ANY CLI
# agent from the ``launch_argv`` recipe below (Gemini, Codex, OpenClaw, …).
AgentKind = Literal["deterministic", "claude", "opencode", "generic_shell", "cao", "headless"]
# How the collector reads the agent's result envelope. ``agent_json`` = tolerant: extract the
# agent's text (from a JSON envelope or nd-JSON stream) then find the {claims:[…]} payload in it.
OutputFormat = Literal["task_result_json", "claude_json", "opencode_json", "agent_json", "none"]
# How a headless agent is pointed at the run-scoped SIFT MCP server. ``claude_flag`` = a
# ``--mcp-config`` flag (Claude-family); ``config_file`` = write the agent's own MCP config
# (per-agent shape; verify-live); ``none`` = no typed tools wired (the agent runs but reaches no
# forensic tools → its claims go unsupported → the floor; honest, never faked).
McpStrategy = Literal["claude_flag", "config_file", "none"]


class AgentProfile(StrictModel):
    """One dispatchable agent profile."""

    profile_id: str
    kind: AgentKind
    model_tier: ModelTier
    cost_class: CostClass
    model: str | None = None  # provider/model id for live agents (None for the deterministic floor)
    command_template: list[str] | None = None  # optional fixed-argv override (generic kind)
    output_format: OutputFormat = "task_result_json"
    max_runtime_seconds: int = Field(default=300, ge=1)
    # Config-driven headless connector recipe (Epic Q; only used by ``kind: headless``).
    launch_argv: list[str] = Field(default_factory=list)  # fixed prefix, e.g. ["gemini", "-p"]
    model_flag: str | None = None  # e.g. "--model"; the model id is appended after it
    extra_argv: list[str] = Field(default_factory=list)  # e.g. ["--output-format", "json"]
    native_tool_argv: list[str] = Field(
        default_factory=list
    )  # per-CLI flags that deny native tools
    auth_env: list[str] = Field(default_factory=list)  # any one present ⇒ authenticated
    mcp_strategy: McpStrategy = "none"
