"""Epic L shared fixtures — thin wrapper over the root ``make_real_run`` factory (M1).

The bypass tests assert the EFFECT of each control against a genuine manifest +
tool_calls.jsonl + claim ledger — never a mock (CLAUDE §2B). No keys, no live agent:
the sandbox is bypass-tested by inspecting the pure argv builder, not by running one.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from siftmesh_core.run_dir import RunPaths

DispatchedCase = Callable[..., tuple[RunPaths, Path]]


@pytest.fixture
def dispatched_case(make_real_run: Callable[..., tuple[RunPaths, Path]]) -> DispatchedCase:
    """Factory: a planned + dispatched run over real fixtures -> (run, evidence_root)."""

    def _make(*, dispatch: bool = True) -> tuple[RunPaths, Path]:
        return make_real_run(dispatch=dispatch)

    return _make
