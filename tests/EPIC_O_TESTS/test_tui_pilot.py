"""Epic O — drive the real Textual app headlessly (skipped if the tui extra is absent).

Uses Textual's `App.run_test()` pilot over the golden run — no real engine, no live agent, no SANS
evidence (§2B). Proves the widgets mount and the cockpit renders a snapshot. The async pilot is run
via `asyncio.run` inside sync tests so no pytest-asyncio plugin is needed.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("textual")

from siftmesh_core.config import load_settings
from siftmesh_core.tui.app import SiftmeshTUI

GOLDEN = Path(__file__).resolve().parents[1] / "golden" / "recorded_run" / "RUN-GOLDEN"


def _drive(app: SiftmeshTUI, scenario: Callable[[Any], Awaitable[None]]) -> None:
    async def run() -> None:
        async with app.run_test() as pilot:
            await pilot.pause()
            await scenario(pilot)

    asyncio.run(run())


def test_cockpit_mounts_and_renders_golden() -> None:
    app = SiftmeshTUI(settings=load_settings(), run_dir=GOLDEN)

    async def scenario(_pilot: Any) -> None:
        from textual.widgets import DataTable, RichLog, Static

        # the first poll ran on mount → the snapshot rendered into the widgets
        table = app.screen.query_one("#tasks", DataTable)
        assert table.row_count == 4  # the golden run's four tasks
        assert app.screen.query_one("#vitals", Static) is not None
        assert app.screen.query_one("#ribbon", Static) is not None
        assert app.screen.query_one("#ticker", RichLog) is not None

    _drive(app, scenario)


def test_home_screen_mounts() -> None:
    app = SiftmeshTUI(settings=load_settings())

    async def scenario(_pilot: Any) -> None:
        from siftmesh_core.tui.app import HomeScreen

        assert isinstance(app.screen, HomeScreen)

    _drive(app, scenario)


def test_onboarding_screen_mounts() -> None:
    app = SiftmeshTUI(settings=load_settings(), start="onboard")

    async def scenario(_pilot: Any) -> None:
        from siftmesh_core.tui.setup_screen import OnboardingScreen
        from textual.widgets import Select, SelectionList

        assert isinstance(app.screen, OnboardingScreen)
        assert app.screen.query_one("#agentsel", SelectionList) is not None  # executor multi-select
        assert (
            app.screen.query_one("#judge", Select) is not None
        )  # Tier-2 judge picker (Epic Q judge)

    _drive(app, scenario)


def test_onboarding_judge_picker_preselects_from_settings() -> None:
    app = SiftmeshTUI(settings=load_settings(judge="cli:gemini"), start="onboard")

    async def scenario(_pilot: Any) -> None:
        from textual.widgets import Select

        assert (
            app.screen.query_one("#judge", Select).value == "cli:gemini"
        )  # pre-selected from config

    _drive(app, scenario)
