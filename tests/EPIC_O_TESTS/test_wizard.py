"""New-investigation wizard — WizardDraft (headless) + the stepped screens (pilot)."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("textual")

from siftmesh_core.config import load_settings
from siftmesh_core.tui.app import SiftmeshTUI
from siftmesh_core.tui.wizard import Step1ProjectScreen, WizardDraft

# ── headless: the load-bearing WizardDraft ───────────────────────────────────


def test_wizard_draft_build_settings_carries_overrides() -> None:
    draft = WizardDraft(
        case_name="c",
        base_dir="/tmp/base",
        agent="gemini",
        judge="cli:gemini",
        max_iterations="5",
        max_agent_tasks="42",
        models={"gemini": "gemini-3-pro"},
        parallel=True,
        all_live=True,
    )
    settings, max_iter = draft.build_settings()
    assert draft.case_dir == "/tmp/base/c"
    assert settings.agent_models.get("gemini_headless") == "gemini-3-pro"
    assert settings.caps.max_agent_tasks == 42
    assert settings.parallel_dispatch is True
    assert settings.live_extraction is True
    assert settings.judge == "cli:gemini"
    assert max_iter == 5


def test_wizard_draft_add_remove_dedupes() -> None:
    draft = WizardDraft()
    assert draft.add_path(Path("/a")) is True
    assert draft.add_path(Path("/a")) is False  # de-duped
    assert draft.add_path(Path("/b")) is True
    draft.remove_path(Path("/a"))
    assert draft.selected_paths == [Path("/b")]


# ── pilot: the screens ───────────────────────────────────────────────────────


def _drive(app: SiftmeshTUI, scenario: Callable[[Any], Awaitable[None]]) -> None:
    async def run() -> None:
        async with app.run_test() as pilot:
            await pilot.pause()
            await scenario(pilot)

    asyncio.run(run())


def test_step1_to_step2_navigation(tmp_path: Path) -> None:
    app = SiftmeshTUI(settings=load_settings())

    async def scenario(pilot: Any) -> None:
        from siftmesh_core.tui.wizard import Step2EvidenceScreen
        from textual.widgets import DirectoryTree, Input

        await pilot.app.push_screen(Step1ProjectScreen(settings=load_settings()))
        await pilot.pause()
        app.screen.query_one("#case", Input).value = "case_x"
        app.screen.query_one("#base", Input).value = str(tmp_path)
        await pilot.pause()
        await pilot.click("#next")
        await pilot.pause()
        assert isinstance(app.screen, Step2EvidenceScreen)
        assert app.screen.draft.case_name == "case_x"
        assert app.screen.query_one("#fstree", DirectoryTree) is not None  # filesystem browser

    _drive(app, scenario)


def test_step2_add_evidence_grows_draft(tmp_path: Path) -> None:
    (tmp_path / "Security.evtx").write_bytes(b"x")
    app = SiftmeshTUI(settings=load_settings())

    async def scenario(pilot: Any) -> None:
        from siftmesh_core.tui.wizard import Step2EvidenceScreen

        draft = WizardDraft(case_name="c", base_dir=str(tmp_path))
        await pilot.app.push_screen(Step2EvidenceScreen(settings=load_settings(), draft=draft))
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, Step2EvidenceScreen)
        screen._current = tmp_path / "Security.evtx"  # simulate a tree selection
        await pilot.click("#add")
        await pilot.pause()
        assert (tmp_path / "Security.evtx") in screen.draft.selected_paths
        from textual.widgets import ListView

        assert screen.query_one("#picked", ListView).children  # rendered in the picked list

    _drive(app, scenario)
