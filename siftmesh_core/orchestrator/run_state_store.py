"""Durable RunState persistence (H1) - crash-safe atomic snapshot.

The Epic-H state machine overwrites ``run_state.json`` on every transition. Writes are
**atomic**: a temp file in the same directory is fully written, ``flush``ed + ``os.fsync``'d,
then ``os.replace`` swaps it into place (atomic rename on POSIX / same filesystem). A reader -
or a run resumed after a crash - therefore always sees a complete, valid snapshot, never a
partial write. Validate-before-write: the model is serialized through Pydantic.
"""

from __future__ import annotations

import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from siftmesh_core.evidence.path_policy import safe_write_path
from siftmesh_core.run_dir import RunPaths
from siftmesh_core.schemas.run import RunState


def write_run_state(run: RunPaths, state: RunState) -> RunState:
    """Atomically persist ``state`` to ``run.run_state``; return the time-stamped snapshot."""
    stamped = state.model_copy(update={"updated_utc": datetime.now(UTC)})
    target = safe_write_path(run.root, Path("run_state.json"))
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = stamped.model_dump_json(indent=2) + "\n"

    fd, tmp_name = tempfile.mkstemp(dir=target.parent, prefix=".run_state-", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        tmp.replace(target)  # atomic rename on the same filesystem (os.replace under the hood)
    finally:
        tmp.unlink(missing_ok=True)  # no-op after a successful replace
    return stamped


def read_run_state(run: RunPaths) -> RunState:
    """Load + validate the persisted RunState; raise ``FileNotFoundError`` if absent."""
    target = run.run_state
    if not target.is_file():
        raise FileNotFoundError(f"no run_state.json at {target}; start the run first")
    return RunState.model_validate_json(target.read_text(encoding="utf-8"))


def run_state_exists(run: RunPaths) -> bool:
    """True if a persisted RunState snapshot exists for this run."""
    return run.run_state.is_file()
