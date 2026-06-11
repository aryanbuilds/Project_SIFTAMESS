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


def test_cockpit_task_and_claim_drilldown_and_console() -> None:
    app = SiftmeshTUI(settings=load_settings(), run_dir=GOLDEN)

    async def scenario(pilot: Any) -> None:
        from siftmesh_core.tui.modals import GateScreen, ReplayScreen, TaskDetailScreen
        from textual.widgets import DataTable, Input, Select

        cockpit = app.screen
        # claim-list tab populated + the filter/ledger controls mounted
        assert cockpit.query_one("#claimlist", DataTable).row_count >= 1
        assert cockpit.query_one("#taskfilter", Input) is not None
        assert cockpit.query_one("#ledgersel", Select) is not None

        # task drill-down: focus + select the first #tasks row + open it (RowSelected on Enter)
        tasks = cockpit.query_one("#tasks", DataTable)
        tasks.focus()
        tasks.move_cursor(row=0)
        await pilot.pause()
        await pilot.press("enter")
        assert isinstance(app.screen, TaskDetailScreen)
        await pilot.press("escape")

        # replay modal
        await pilot.press("p")
        assert isinstance(app.screen, ReplayScreen)
        await pilot.press("escape")

        # gate selector pops up
        await pilot.press("g")
        assert isinstance(app.screen, GateScreen)
        await pilot.press("escape")

        # task filter narrows the table
        full = cockpit.query_one("#tasks", DataTable).row_count
        cockpit.query_one("#taskfilter", Input).value = "ZZZ-no-match"
        await pilot.pause()
        assert cockpit.query_one("#tasks", DataTable).row_count == 0
        cockpit.query_one("#taskfilter", Input).value = ""
        await pilot.pause()
        assert cockpit.query_one("#tasks", DataTable).row_count == full

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


def test_onboarding_shows_tier_legend_and_remediation() -> None:
    # The guided wizard must render the honest T0-T3 legend + a fix-it block (no live agent needed).
    app = SiftmeshTUI(settings=load_settings(), start="onboard")

    async def scenario(_pilot: Any) -> None:
        from textual.widgets import Static

        guidance = app.screen.query_one("#guidance", Static)
        text = str(guidance.render())  # Static has no .renderable in textual 8.2.7 — use render()
        assert "Safety tiers" in text
        assert "T2 unconstrained_live" in text  # the legend is shown
        # either a remediation block (something not ready) or the ready CTA — both are honest states
        assert ("To make an agent ready:" in text) or ("Ready:" in text)

    _drive(app, scenario)


def test_new_run_screen_shows_mode_help_and_agent_tiers() -> None:
    app = SiftmeshTUI(settings=load_settings())

    async def scenario(pilot: Any) -> None:
        from siftmesh_core.tui.launcher_screen import NewRunScreen
        from textual.widgets import Select, Static

        await pilot.app.push_screen(NewRunScreen(settings=load_settings()))
        await pilot.pause()
        assert "auto" in str(app.screen.query_one("#modehelp", Static).render())
        assert app.screen.query_one("#agenthelp", Static) is not None
        # the floor option carries its [T0] tier label
        agent = app.screen.query_one("#agent", Select)
        labels = [str(prompt) for prompt, _ in agent._options]  # type: ignore[attr-defined]
        assert any("[T0]" in label for label in labels)

    _drive(app, scenario)
