"""Onboarding Tier-2 judge tab: provider radio drives key-input visibility + persists the judge."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("textual")

from siftmesh_core.config import load_settings
from siftmesh_core.tui.app import SiftmeshTUI


@pytest.fixture(autouse=True)
def _isolate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    (tmp_path / "home").mkdir()
    monkeypatch.chdir(tmp_path)


def _drive(app: SiftmeshTUI, scenario: Callable[[Any], Awaitable[None]]) -> None:
    async def run() -> None:
        async with app.run_test() as pilot:
            await pilot.pause()
            await scenario(pilot)

    asyncio.run(run())


def test_cli_judge_hides_key_input_and_saves() -> None:
    app = SiftmeshTUI(settings=load_settings(), start="onboard")

    async def scenario(pilot: Any) -> None:
        from textual.widgets import Button, Input, RadioButton

        screen = app.screen
        screen.query_one("#j-claude", RadioButton).value = True
        await pilot.pause()
        assert screen.query_one("#apikey", Input).display is False  # cli backend → no key input
        assert screen.query_one("#launchjudgeauth", Button).display is True  # login button shown
        screen._save_judge()
        await pilot.pause()
        from siftmesh_core.config import load_settings as reload

        assert reload().judge == "cli:claude"

    _drive(app, scenario)


def test_litellm_judge_shows_key_input() -> None:
    app = SiftmeshTUI(settings=load_settings(), start="onboard")

    async def scenario(pilot: Any) -> None:
        from textual.widgets import Input, RadioButton

        screen = app.screen
        screen.query_one("#j-gemini", RadioButton).value = True
        await pilot.pause()
        assert screen.query_one("#apikey", Input).display is True  # litellm → key input visible
        assert screen.query_one("#litemodel", Input).value  # model prefilled (gemini/...)

    _drive(app, scenario)


def test_tier1_only_saves_none() -> None:
    app = SiftmeshTUI(settings=load_settings(judge="cli:claude"), start="onboard")

    async def scenario(pilot: Any) -> None:
        from textual.widgets import RadioButton

        screen = app.screen
        screen.query_one("#j-none", RadioButton).value = True
        await pilot.pause()
        screen._save_judge()
        await pilot.pause()
        from siftmesh_core.config import load_settings as reload

        s = reload()
        assert s.judge is None
        assert s.llm_critic_enabled is False

    _drive(app, scenario)
