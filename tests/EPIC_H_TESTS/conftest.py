"""Epic H shared fixtures - engine-ready runs built on the root factory (M1).

``built_run`` adds the one Epic-H-specific stage on top of the shared no-plan run:
an initial persisted ``RunState``, so ``run_engine`` can drive the full state machine
(create_evidence_vault → plan → dispatch → collect → critique → decide → report →
done) over the committed public fixtures. No keys, no live agent.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from siftmesh_core.orchestrator.run_state_store import write_run_state
from siftmesh_core.run_dir import RunPaths
from siftmesh_core.schemas.run import RunMode, RunState

# Factory: (mode, max_iterations) -> an engine-ready run + its evidence root.
BuiltRun = Callable[..., tuple[RunPaths, Path]]


@pytest.fixture
def built_run(make_real_run: Callable[..., tuple[RunPaths, Path]]) -> BuiltRun:
    """Factory: an init-ready run (manifest + readonly + RunState) → (run, evidence_root)."""

    def _make(*, mode: RunMode = "auto", max_iterations: int = 3) -> tuple[RunPaths, Path]:
        run, evidence = make_real_run(plan=False)  # the engine itself plans/dispatches
        write_run_state(run, RunState(run_id=run.run_id, mode=mode, max_iterations=max_iterations))
        return run, evidence

    return _make


@pytest.fixture
def evidence_dir(tmp_path: Path, build_evidence: Callable[..., None]) -> Path:
    """A read-only evidence dir of real fixtures, for `siftmesh run` CLI tests (init-case)."""
    evidence = tmp_path / "evidence"
    build_evidence(evidence)
    return evidence
