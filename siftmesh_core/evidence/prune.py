"""Prune a completed run's bulky derived data (scale fixes / PLAN 11).

A run's ``evidence/extracted/`` holds the large derived artifacts (a ~19 GB decompressed memory
image, disk-extracted files) written BY DESIGN under the run dir (originals are read-only). Once a
run is done and reported, those bytes can be reclaimed while every ledger / report / manifest is
kept — so the run still merges and replays. This is what makes the "run → prune → next portion →
merge" workflow safe and auditable. Refuses a non-terminal run unless forced.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from siftmesh_core.evidence.path_policy import safe_write_path
from siftmesh_core.ledgers.audit_log import log_event, open_orchestration_log
from siftmesh_core.orchestrator.run_state_store import read_run_state
from siftmesh_core.run_dir import RunPaths

_EXTRACTED = Path("evidence") / "extracted"


class PrunePolicyError(RuntimeError):
    """Refused to prune (e.g. a non-terminal run without --force)."""


@dataclass(frozen=True)
class PruneOutcome:
    files_removed: int
    bytes_freed: int


def prune_run(run: RunPaths, *, force: bool = False) -> PruneOutcome:
    """Delete ``evidence/extracted/`` (derived bulk); keep all ledgers/reports. Audited."""
    if run.run_state.is_file():
        state = read_run_state(run)
        if not state.terminal and not force:
            raise PrunePolicyError(
                f"run {run.run_id} is not terminal (state={state.state}); pass --force to prune"
            )
    extracted = safe_write_path(run.root, _EXTRACTED)  # confine to the run dir
    files_removed = 0
    bytes_freed = 0
    if extracted.is_dir():
        for p in extracted.rglob("*"):
            if p.is_file():
                files_removed += 1
                bytes_freed += p.stat().st_size
        shutil.rmtree(extracted)
    audit = open_orchestration_log(run.orchestration_events, run.run_id)
    log_event(audit, "derived_pruned", files_removed=files_removed, bytes_freed=bytes_freed)
    return PruneOutcome(files_removed=files_removed, bytes_freed=bytes_freed)
