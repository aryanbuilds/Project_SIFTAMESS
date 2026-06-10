"""Epic J shared fixtures — thin wrappers over the root ``make_real_run`` factory (M1).

``dispatched_run`` is a real planned + dispatched + critiqued run over the committed
public fixtures (real Epic-D tools → real claims/tool_calls/verdicts), so reports
render from a genuine ledger set. ``planned_run`` is plan-only (no execution) for the
empty/halted edge cases. No keys, no live agent.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from siftmesh_core.run_dir import RunPaths

Case = Callable[..., tuple[RunPaths, Path]]


@pytest.fixture
def dispatched_run(make_real_run: Callable[..., tuple[RunPaths, Path]]) -> Case:
    """Factory: a real planned + dispatched + critiqued run → (run, evidence_root)."""

    def _make(*, critique: bool = True) -> tuple[RunPaths, Path]:
        return make_real_run(dispatch=True, critique=critique)

    return _make


@pytest.fixture
def planned_run(make_real_run: Callable[..., tuple[RunPaths, Path]]) -> Case:
    """Factory: a sealed + planned run with NO execution (empty ledgers) → (run, evidence_root)."""

    def _make() -> tuple[RunPaths, Path]:
        return make_real_run()

    return _make
