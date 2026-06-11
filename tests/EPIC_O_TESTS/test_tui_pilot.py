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
        from textual.widgets import (
            DataTable,
            LoadingIndicator,
            ProgressBar,
            RichLog,
            Static,
            TabbedContent,
        )

        # the first poll ran on mount → the snapshot rendered into the redesigned widgets
        table = app.screen.query_one("#tasks", DataTable)
        assert table.row_count == 4  # the golden run's four tasks
        assert app.screen.query_one("#vitals", Static) is not None
        assert app.screen.query_one("#ribbon", Static) is not None
        assert app.screen.query_one("#ticker", RichLog) is not None
        # redesign: progress bar + tabbed side panel (3 tabs) + loading indicator
        bar = app.screen.query_one("#taskbar", ProgressBar)
        assert bar.total == 4  # tasks_total from the golden snapshot
        assert app.screen.query_one("#side", TabbedContent) is not None
        for tab in ("#claims", "#agents", "#budget"):
            assert app.screen.query_one(tab, Static) is not None
        assert app.screen.query_one("#loading", LoadingIndicator).display is False

    _drive(app, scenario)


def test_app_registers_siftmesh_themes() -> None:
    app = SiftmeshTUI(settings=load_settings(), run_dir=GOLDEN)

    async def scenario(_pilot: Any) -> None:
        assert app.theme == "siftmesh-dark"  # default on_mount
        assert "siftmesh-dark" in app.available_themes
        assert "siftmesh-light" in app.available_themes
        app.action_toggle_theme()
        assert app.theme == "siftmesh-light"  # ctrl+t toggles

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
        # per-provider model inputs (Epic O redesign — finer control)
        from textual.widgets import Input

        for name in ("claude", "gemini", "codex", "opencode"):
            assert app.screen.query_one(f"#model-{name}", Input) is not None

    _drive(app, scenario)


def test_onboarding_model_input_prefills_from_settings() -> None:
    app = SiftmeshTUI(
        settings=load_settings(agent_models={"gemini_headless": "gemini-3-pro"}), start="onboard"
    )

    async def scenario(_pilot: Any) -> None:
        from textual.widgets import Input

        assert app.screen.query_one("#model-gemini", Input).value == "gemini-3-pro"

    _drive(app, scenario)


def test_onboarding_judge_picker_preselects_from_settings() -> None:
    app = SiftmeshTUI(settings=load_settings(judge="cli:gemini"), start="onboard")

    async def scenario(_pilot: Any) -> None:
        from textual.widgets import Select

        assert (
            app.screen.query_one("#judge", Select).value == "cli:gemini"
        )  # pre-selected from config

    _drive(app, scenario)
