"""Decision schema (Epic G, G4) — the pure DECIDE function's output.

``decide()`` (``orchestrator/decide.py``) maps a critic verdict + run/task facts to
one of four actions per CLAUDE.md §12. The model is intentionally minimal and
carries no I/O state so ``decide`` stays a pure function.
"""

from __future__ import annotations

from typing import Literal

from siftmesh_core.schemas._base import StrictModel

DecisionAction = Literal["done", "retry", "escalate", "human_review", "follow_up"]


class Decision(StrictModel):
    """What the deterministic engine should do next with a task (CLAUDE §12)."""

    action: DecisionAction
    reason: str
    # True only when action == "retry": the retry contract tightens success_criteria (G5).
    tighten_success_criteria: bool = False
