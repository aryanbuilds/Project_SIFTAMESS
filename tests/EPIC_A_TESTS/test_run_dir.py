"""A4: run-directory generator — full subtree, UTC ids, collision-safe."""

from __future__ import annotations

import re
from pathlib import Path

from siftmesh_core.run_dir import RUN_SUBDIRS, new_run_dir, utc_run_id


def test_creates_full_subtree(tmp_path: Path) -> None:
    rp = new_run_dir(base=tmp_path)
    assert rp.root.is_dir()
    for sub in RUN_SUBDIRS:
        assert (rp.root / sub).is_dir(), f"missing subdir: {sub}"
    assert len(rp.subdirs()) == 7


def test_run_id_is_utc_format() -> None:
    assert re.fullmatch(r"RUN-\d{8}-\d{6}", utc_run_id())


def test_collision_safe_second_call(tmp_path: Path) -> None:
    name = "RUN-20260101-000000"
    first = new_run_dir(base=tmp_path, run_name=name)
    second = new_run_dir(base=tmp_path, run_name=name)
    assert first.root != second.root
    assert first.root.is_dir() and second.root.is_dir()
    assert second.root.name == f"{name}-01"


def test_custody_log_path_under_evidence(tmp_path: Path) -> None:
    rp = new_run_dir(base=tmp_path)
    assert rp.custody_log == rp.evidence / "custody_log.jsonl"
    assert rp.custody_log.parent.is_dir()
