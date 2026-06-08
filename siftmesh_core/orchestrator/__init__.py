"""SIFTMesh orchestration core (Epic E onward).

Epic E ships the deterministic Planner + Deep Context Agent: it turns an evidence
manifest into context packets, an investigation plan, and task contracts — with no
live LLM. The privilege rule is load-bearing: the planner *proposes*, it never
executes a tool and never reads an evidence byte (it reads manifest metadata only).
"""

from __future__ import annotations

from siftmesh_core.orchestrator.planner import PlanResult, generate_plan

__all__ = ["PlanResult", "generate_plan"]
