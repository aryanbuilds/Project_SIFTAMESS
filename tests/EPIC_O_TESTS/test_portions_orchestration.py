"""Portions→prune→merge orchestration (TUI low-disk path) - headless, deterministic floor.

`actions.run_in_portions` curates each portion's subset, runs it to terminal, prunes its derived
bulk, then merges the runs into one report. No Textual, no live agent, no keys.
"""

from __future__ import annotations

from pathlib import Path

from siftmesh_core.config import load_settings
from siftmesh_core.run_dir import RunPaths
from siftmesh_core.tui import actions


class _Item:
    """Minimal stand-in for a space.SpaceItem (run_in_portions only reads .path)."""

    def __init__(self, path: str) -> None:
        self.path = path


def test_two_portions_run_prune_merge(make_real_run, tmp_path) -> None:  # type: ignore[no-untyped-def]
    # Build a real evidence dir (committed fixtures) to source the portions from.
    _run, evidence = make_real_run(plan=True)
    files = sorted(p.name for p in Path(evidence).iterdir() if p.is_file())
    assert len(files) >= 2, "need >=2 evidence files to split into 2 portions"

    # Split the evidence files into two portions (one file each, rest in portion 2).
    plan = [[_Item(files[0])], [_Item(f) for f in files[1:]]]
    progress: list[str] = []
    seen_runs: list[RunPaths] = []

    case_dir = str(tmp_path / "case_portions")
    res = actions.run_in_portions(
        case_dir,
        plan,
        str(evidence),
        settings=load_settings(),
        mode="auto",
        progress=progress.append,
        on_run=seen_runs.append,
    )

    assert res.ok, res.message
    assert len(seen_runs) == 2  # two portion runs were created + driven
    for run in seen_runs:
        assert (run.root / "run_state.json").is_file()  # each portion is its own resumable run
        assert not (run.root / "evidence" / "extracted").exists()  # pruned (nothing extracted here)
    assert "merged 2 portions" in res.message
    assert any("portion 1/2" in m for m in progress)


def test_single_portion_skips_merge(make_real_run, tmp_path) -> None:  # type: ignore[no-untyped-def]
    _run, evidence = make_real_run(plan=True)
    one = next(p.name for p in Path(evidence).iterdir() if p.is_file())
    res = actions.run_in_portions(
        str(tmp_path / "case_one"),
        [[_Item(one)]],
        str(evidence),
        settings=load_settings(),
        mode="auto",
    )
    assert res.ok
    assert "single portion complete" in res.message  # merge requires >=2 sources
