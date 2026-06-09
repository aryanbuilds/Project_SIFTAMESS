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
AgentKind = Literal["deterministic", "claude", "opencode", "generic_shell", "cao"]
# How the collector reads the agent's result envelope.
OutputFormat = Literal["task_result_json", "claude_json", "opencode_json", "none"]


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
