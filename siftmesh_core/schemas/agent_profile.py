"""Agent-profile schema (C5) — a dispatchable agent's identity + cost class.

SIFTMesh is agent-agnostic, so ``kind`` is an open string (claude_code, opencode,
codex, gemini, a deterministic local profile, ...). ``model_tier`` / ``cost_class``
drive the Budget Router. Schema only — the profile registry is Epic I.
"""

from __future__ import annotations

from typing import Literal

from siftmesh_core.schemas._base import StrictModel

ModelTier = Literal["high", "low", "local"]
CostClass = Literal["expensive", "cheap", "free"]


class AgentProfile(StrictModel):
    """One dispatchable agent profile."""

    profile_id: str
    kind: str
    model_tier: ModelTier
    cost_class: CostClass
