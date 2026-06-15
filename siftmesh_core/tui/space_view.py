"""Pre-run readiness synthesis (TUI wizard, Textual-FREE) - verify host + estimate space → options.

``build_readiness`` composes the EXISTING primitives - ``doctor.collect_checks`` (host/backends),
``doctor.probe_agents`` (which agent will run), and ``evidence.space.estimate_required``
(derived-data size vs free disk) - into one ``ReadinessReport`` the wizard's Verify+Space step
renders. When the
evidence won't fit, it carries the ``partition_plan`` portions (the run-in-portions path) using the
SAME math as the CLI's ``_space_preflight_ok``. Pure → unit-tested without a terminal.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from siftmesh_core.config import SiftmeshSettings
from siftmesh_core.doctor import collect_checks, probe_agents
from siftmesh_core.evidence.space import (
    SpaceEstimate,
    SpaceItem,
    estimate_required,
    human_bytes,
    partition_plan,
)
from siftmesh_core.schemas.agent_capabilities import AgentCapabilityMap


@dataclass(frozen=True)
class ReadinessReport:
    """Everything the Verify+Space step shows: host checks, agent, size vs free, recommendation."""

    estimate: SpaceEstimate
    agents: AgentCapabilityMap
    checks_ok: int
    checks_warn: int
    checks_fail: int
    check_lines: tuple[str, ...]  # "fail|warn|ok  <name>: <detail>" (fails+warns first)
    portions: tuple[tuple[SpaceItem, ...], ...]  # non-empty only when NOT fits
    recommendation: str  # "full" | "single" | "portions"

    @property
    def fits(self) -> bool:
        return self.estimate.fits

    @property
    def needed_human(self) -> str:
        return human_bytes(self.estimate.needed_bytes)

    @property
    def free_human(self) -> str:
        return human_bytes(self.estimate.free_bytes)

    @property
    def blocking(self) -> bool:
        """A FAIL check means the host can't run (fail-closed) - the wizard must not launch."""
        return self.checks_fail > 0


def build_readiness(
    evidence_dir: Path | str,
    *,
    run_location: Path | str = ".",
    settings: SiftmeshSettings | None = None,
) -> ReadinessReport:
    """Synthesize host verification + space availability into one report with a recommendation."""
    from siftmesh_core.config import load_settings

    settings = settings or load_settings()
    estimate = estimate_required(evidence_dir, run_location=run_location)
    agents = probe_agents(settings)
    checks = collect_checks(settings)

    ok = sum(1 for c in checks if c.status == "ok")
    warn = sum(1 for c in checks if c.status == "warn")
    fail = sum(1 for c in checks if c.status == "fail")
    rank = {"fail": 0, "warn": 1, "ok": 2}
    ordered = sorted(checks, key=lambda c: (rank.get(c.status, 3), c.name))
    lines = tuple(f"{c.status}  {c.name}: {c.detail}" for c in ordered)

    if not estimate.fits:
        sized = [i for i in estimate.items if i.derived_bytes]
        budget = int(estimate.free_bytes / 1.2)  # same safety margin as needed_bytes
        portions = tuple(tuple(p) for p in partition_plan(sized, budget))
        recommendation = "portions"
    else:
        portions = ()
        recommendation = "full" if agents.live_candidate else "single"

    return ReadinessReport(
        estimate=estimate,
        agents=agents,
        checks_ok=ok,
        checks_warn=warn,
        checks_fail=fail,
        check_lines=lines,
        portions=portions,
        recommendation=recommendation,
    )
