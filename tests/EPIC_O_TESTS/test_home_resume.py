"""Home run-list badges + one-click Resume (run_badge / resumable + the Resume button)."""

from __future__ import annotations

import shutil
from pathlib import Path

from siftmesh_core.orchestrator.run_state_store import write_run_state
from siftmesh_core.run_dir import RunPaths
from siftmesh_core.schemas.run import RunState
from siftmesh_core.tui.snapshot import resumable, run_badge

GOLDEN = Path(__file__).resolve().parents[1] / "golden" / "recorded_run" / "RUN-GOLDEN"


def test_badge_new_when_no_state(tmp_path: Path) -> None:
    run = RunPaths(root=tmp_path / "RUN-EMPTY")
    run.root.mkdir(parents=True)
    assert run_badge(run) == "new"
    assert resumable(run) is False


def test_badge_terminal_and_blocked_and_running(tmp_path: Path) -> None:
    term = RunPaths(root=tmp_path / "RUN-TERM")
    term.root.mkdir(parents=True)
    write_run_state(term, RunState(run_id=term.run_id, mode="auto", state="done", terminal=True))
    assert run_badge(term) == "terminal"
    assert resumable(term) is False

    blocked = RunPaths(root=tmp_path / "RUN-BLOCK")
    blocked.root.mkdir(parents=True)
    write_run_state(
        blocked,
        RunState(
            run_id=blocked.run_id, mode="auto_human_loop", state="decide", blocked_gate="retry"
        ),
    )
    assert run_badge(blocked) == "blocked:retry"
    assert resumable(blocked) is True

    running = RunPaths(root=tmp_path / "RUN-RUN")
    running.root.mkdir(parents=True)
    write_run_state(running, RunState(run_id=running.run_id, mode="auto", state="dispatch"))
    assert run_badge(running) == "running"
    assert resumable(running) is True


def test_home_screen_has_resume_button_and_badge(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import asyncio

    from siftmesh_core.config import load_settings
    from siftmesh_core.run_dir import DEFAULT_BASE
    from siftmesh_core.tui.app import HomeScreen, SiftmeshTUI

    # Point the home run-picker at a base dir holding one golden (terminal) run.
    base = tmp_path / "case_runs"
    shutil.copytree(GOLDEN, base / "RUN-GOLDEN")
    monkeypatch.setattr("siftmesh_core.tui.app.DEFAULT_BASE", str(base))
    assert Path(DEFAULT_BASE)  # sanity: symbol exists

    app = SiftmeshTUI(settings=load_settings())

    async def run() -> None:
        async with app.run_test() as pilot:
            await pilot.pause()
            from textual.widgets import Button, ListView

            assert isinstance(app.screen, HomeScreen)
            assert app.screen.query_one("#resume", Button) is not None
            lv = app.screen.query_one("#runs", ListView)
            assert lv.children  # the golden run listed (with a badge appended to its label)

    asyncio.run(run())
