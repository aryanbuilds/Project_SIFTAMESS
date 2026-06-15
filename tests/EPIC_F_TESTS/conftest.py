"""Epic F shared fixtures - thin wrapper over the root ``make_real_run`` factory (M1).

The deterministic executor runs the real Epic-D tools, so these tests need real
artifact bytes (incl. ``$MFT`` for the timeline lane). No keys, no live agent.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from siftmesh_core.run_dir import RunPaths

RealCase = Callable[..., tuple[RunPaths, Path]]


@pytest.fixture
def real_case(make_real_run: Callable[..., tuple[RunPaths, Path]]) -> RealCase:
    """Factory: build a planned run over the real fixtures; return (run, evidence_root)."""

    def _make(*, review_only: bool = False) -> tuple[RunPaths, Path]:
        return make_real_run(plan=True, review_only=review_only, with_mft=True)

    return _make
