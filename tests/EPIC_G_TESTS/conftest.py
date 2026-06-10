"""Epic G shared fixtures — thin wrapper over the root ``make_real_run`` factory (M1).

A planned + dispatched run (real Epic-D tools over the committed public fixtures),
so the critic has a real manifest + tool_calls.jsonl + claim ledger to validate
against. Crafted TaskResults (rejection/retry/injection tests) are written into
this real run. No keys, no live agent — governance tests only.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from siftmesh_core.run_dir import RunPaths

DispatchedCase = Callable[..., tuple[RunPaths, Path]]


@pytest.fixture
def dispatched_case(make_real_run: Callable[..., tuple[RunPaths, Path]]) -> DispatchedCase:
    """Factory: a planned + dispatched run over real fixtures → (run, evidence_root)."""

    def _make(*, dispatch: bool = True) -> tuple[RunPaths, Path]:
        return make_real_run(dispatch=dispatch)

    return _make
