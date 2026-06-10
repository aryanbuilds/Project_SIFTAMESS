"""Pre-flight space estimator + partition planner + prune (scale fixes / PLAN 11)."""

from __future__ import annotations

import zipfile
from collections.abc import Callable
from pathlib import Path

from siftmesh_core.evidence.prune import PrunePolicyError, prune_run
from siftmesh_core.evidence.space import (
    SpaceItem,
    estimate_required,
    human_bytes,
    partition_plan,
)
from siftmesh_core.evidence.vault import init_case
from siftmesh_core.orchestrator.run_state_store import read_run_state, write_run_state


def test_zip_uncompressed_size_is_exact(tmp_path: Path) -> None:
    ev = tmp_path / "ev"
    ev.mkdir()
    payload = b"A" * 50_000
    with zipfile.ZipFile(ev / "cap.zip", "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("mem.raw", payload)  # highly compressible → big uncompressed/compressed gap
    est = estimate_required(ev, run_location=tmp_path)
    item = next(i for i in est.items if i.path == "cap.zip")
    assert item.exact is True
    assert item.derived_bytes == len(payload)  # exact uncompressed size from the zip header


def test_nested_archive_zip_is_estimated(tmp_path: Path) -> None:
    ev = tmp_path / "ev"
    ev.mkdir()
    with zipfile.ZipFile(ev / "cap.zip", "w") as zf:
        zf.writestr("inner.7z", b"7z\xbc\xaf\x27\x1c" + b"\x00" * 1000)  # nested archive member
    est = estimate_required(ev, run_location=tmp_path)
    item = next(i for i in est.items if i.path == "cap.zip")
    assert item.exact is False  # zip→inner-archive→bigger raw: can't read the inner header cheaply
    assert item.derived_bytes > 0


def test_partition_plan_ffd_fits_budget() -> None:
    items = [
        SpaceItem(path=f"a{i}.zip", base_bytes=0, derived_bytes=size, exact=True)
        for i, size in enumerate([900, 800, 500, 400, 300])
    ]
    portions = partition_plan(items, budget_bytes=1000)
    assert all(sum(it.derived_bytes for it in p) <= 1000 for p in portions)
    # all items placed exactly once
    assert sorted(it.path for p in portions for it in p) == sorted(it.path for it in items)


def test_human_bytes() -> None:
    assert human_bytes(0) == "0 B"
    assert human_bytes(1536).endswith("KB")
    assert human_bytes(5 * 1024**3).endswith("GB")


def test_prune_removes_extracted_keeps_ledgers(
    tmp_path: Path, build_evidence: Callable[..., None]
) -> None:
    ev = tmp_path / "ev"
    build_evidence(ev)
    run = init_case(tmp_path / "case", ev)
    # simulate a derived bulk + a terminal run
    extracted = run.evidence / "extracted"
    extracted.mkdir(parents=True)
    (extracted / "Rocba-Memory.raw").write_bytes(b"\x00" * 100_000)
    state = read_run_state(run) if run.run_state.is_file() else None
    if state is None:
        from siftmesh_core.schemas.run import RunState

        state = RunState(run_id=run.run_id, mode="auto", state="done", terminal=True)
    write_run_state(run, state.model_copy(update={"state": "done", "terminal": True}))

    outcome = prune_run(run)
    assert outcome.files_removed == 1
    assert outcome.bytes_freed == 100_000
    assert not extracted.exists()  # bulky derived gone
    assert run.evidence_manifest.is_file()  # ledgers/manifest kept
    assert "derived_pruned" in run.orchestration_events.read_text(encoding="utf-8")


def test_prune_refuses_non_terminal(tmp_path: Path, build_evidence: Callable[..., None]) -> None:
    ev = tmp_path / "ev"
    build_evidence(ev)
    run = init_case(tmp_path / "case", ev)
    from siftmesh_core.schemas.run import RunState

    write_run_state(run, RunState(run_id=run.run_id, mode="auto", state="dispatch", terminal=False))
    try:
        prune_run(run)
    except PrunePolicyError:
        return
    raise AssertionError("prune should refuse a non-terminal run without --force")
