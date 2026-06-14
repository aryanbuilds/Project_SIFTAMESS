"""New-investigation wizard — WizardDraft (headless) + the hybrid 2-screen flow (pilot)."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("textual")

from siftmesh_core.config import load_settings
from siftmesh_core.tui.app import SiftmeshTUI
from siftmesh_core.tui.wizard import RunSetupScreen, WizardDraft, resolve_brief_path

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


def test_setup_screen_browses_above_project_root(tmp_path: Path) -> None:
    """The evidence DirectoryTree must be re-rootable anywhere (the bug: stuck at base_dir)."""
    app = SiftmeshTUI(settings=load_settings())

    async def scenario(pilot: Any) -> None:
        from textual.widgets import DirectoryTree, Input, OptionList

        await pilot.app.push_screen(RunSetupScreen(settings=load_settings()))
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, RunSetupScreen)
        tree = screen.query_one("#fstree", DirectoryTree)
        # default root is HOME (above any project dir), not the cwd
        assert str(tree.path) == str(Path.home())
        # re-root to an arbitrary path ABOVE/aside the project (the fix)
        screen.query_one("#evroot", Input).value = str(tmp_path)
        screen._reroot(tmp_path)
        await pilot.pause()
        assert str(tree.path) == str(tmp_path.resolve())
        assert screen.query_one("#evhits", OptionList) is not None  # fuzzy results widget present

    _drive(app, scenario)


def test_setup_add_evidence_grows_draft(tmp_path: Path) -> None:
    (tmp_path / "Security.evtx").write_bytes(b"x")
    app = SiftmeshTUI(settings=load_settings())

    async def scenario(pilot: Any) -> None:
        from textual.widgets import ListView

        draft = WizardDraft(case_name="c", base_dir=str(tmp_path))
        await pilot.app.push_screen(RunSetupScreen(settings=load_settings(), draft=draft))
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, RunSetupScreen)
        screen._set_current(tmp_path / "Security.evtx")  # simulate a tree selection
        await pilot.click("#add")
        await pilot.pause()
        assert (tmp_path / "Security.evtx") in screen.draft.selected_paths
        assert screen.query_one("#picked", ListView).children  # rendered in the picked list


def test_setup_fuzzy_search_populates_and_adds(tmp_path: Path) -> None:
    (tmp_path / "Security.evtx").write_bytes(b"x")
    (tmp_path / "System.evtx").write_bytes(b"x")
    app = SiftmeshTUI(settings=load_settings())

    async def scenario(pilot: Any) -> None:
        from textual.widgets import OptionList

        draft = WizardDraft(case_name="c", base_dir=str(tmp_path))
        screen = RunSetupScreen(settings=load_settings(), draft=draft)
        await pilot.app.push_screen(screen)
        await pilot.pause()
        screen.query_one("#evroot").value = str(tmp_path)
        screen._search("#file evtx")  # kicks the worker
        # wait for the @work(thread) result to land
        for _ in range(40):
            await pilot.pause()
            if screen._hits:
                break
        assert screen._hits, "fuzzy search returned no hits"
        opts = app.screen.query_one("#evhits", OptionList)
        assert opts.option_count >= 2
        # selecting a hit adds it to the picked list (Enter on a result → _add_hit)
        screen._add_hit(0)
        assert screen._hits[0] in screen.draft.selected_paths

    _drive(app, scenario)


# ── brief selection: full resolved path (not a bare filename) + reuse the fuzzy/tree picker ──


def test_resolve_brief_path_relative_absolute_and_missing(tmp_path: Path) -> None:
    brief = tmp_path / "ROCBA-BACKGROUND.pptx"
    brief.write_bytes(b"x")
    # a bare filename resolves under the browse root to its full absolute path
    assert resolve_brief_path("ROCBA-BACKGROUND.pptx", tmp_path) == str(brief.resolve())
    # an absolute path passes through (browse root irrelevant)
    assert resolve_brief_path(str(brief), "/nonexistent") == str(brief.resolve())
    # a missing brief is rejected (None) so _next can stop with an error
    assert resolve_brief_path("nope.pptx", tmp_path) is None


def test_set_brief_captures_full_path_and_drops_from_evidence(tmp_path: Path) -> None:
    brief = tmp_path / "brief.pptx"
    brief.write_bytes(b"x")
    app = SiftmeshTUI(settings=load_settings())

    async def scenario(pilot: Any) -> None:
        draft = WizardDraft(case_name="c", base_dir=str(tmp_path))
        screen = RunSetupScreen(settings=load_settings(), draft=draft)
        await pilot.app.push_screen(screen)
        await pilot.pause()
        screen._set_current(brief)  # a tree/fuzzy selection
        screen.draft.add_path(brief)  # pretend the fuzzy hit had added it to evidence
        await pilot.click("#setbrief")
        await pilot.pause()
        assert screen.draft.brief_path == str(brief.resolve())  # full resolved path, not a filename
        assert brief not in screen.draft.selected_paths  # a brief is never also evidence
        assert brief.resolve() not in screen.draft.selected_paths

    _drive(app, scenario)
