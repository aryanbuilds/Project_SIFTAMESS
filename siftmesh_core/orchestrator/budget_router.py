"""Static budget router (H9, MVP-light) - escalate cheap→strong on retry/contradiction.

A real, self-contained routing decision recorded to ``audit/token_budget.jsonl``. Until Epic I
ships ``agent_profiles.yaml``, the tier map is a small static table: the deterministic floor maps
to itself (escalation is a logged no-op there - honest, the executor stays the floor until the live
agent is wired), and a documented cheap→strong pair applies once a live profile is configured.
Absent a strong tier, it falls back to the base profile (graceful default).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from siftmesh_core.evidence.path_policy import safe_write_path
from siftmesh_core.run_dir import RunPaths

# base profile -> escalated (strong) profile. Static until Epic I's agent_profiles.yaml.
_ESCALATION: dict[str, str] = {
    "deterministic_executor": "deterministic_executor",  # the floor has no stronger tier
    "claude_low_cost": "claude_high_reasoning",
    "opencode_low_cost": "claude_high_reasoning",
}


@dataclass(frozen=True)
class RoutingDecision:
    """One budget-routing decision (which profile to run, and whether it escalated)."""

    base_profile: str
    selected_profile: str
    escalated: bool
    reason: str


def select_profile(base_profile: str, *, escalate: bool, reason: str = "") -> RoutingDecision:
    """Choose the executor profile; escalate cheap->strong on request (graceful default)."""
    if not escalate:
        return RoutingDecision(base_profile, base_profile, False, reason or "no escalation")
    strong = _ESCALATION.get(base_profile, base_profile)
    return RoutingDecision(
        base_profile, strong, strong != base_profile, reason or "retry/contradiction"
    )


def record_routing(
    run: RunPaths, decision: RoutingDecision, *, evidence_root: Path | str | None = None
) -> Path:
    """Append one routing decision to ``audit/token_budget.jsonl``."""
    target = safe_write_path(
        run.root, Path("audit") / "token_budget.jsonl", evidence_root=evidence_root
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "base_profile": decision.base_profile,
        "selected_profile": decision.selected_profile,
        "escalated": decision.escalated,
        "reason": decision.reason,
        "recorded_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }
    with target.open("a", encoding="utf-8", newline="\n") as out:
        out.write(json.dumps(payload) + "\n")
    return target
